# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import typing

@allow_storage
@dataclass
class FactCheckRecord:
    initiator: str
    target_link: str
    statement: str
    current_state: str
    decision_rationale: str
    page_excerpt: str

class WebFactChecker(gl.Contract):
    """On-chain AI Fact Checker: verifies if a web page supports a given statement."""

    check_tasks: TreeMap[str, FactCheckRecord]

    def __init__(self):
        pass

    def _get_task(self, task_id: str) -> FactCheckRecord:
        if task_id not in self.check_tasks:
            raise Exception("Task ID not found: " + task_id)
        return self.check_tasks[task_id]

    def _verify_url_format(self, url_str: str) -> str:
        clean_url = url_str.strip()
        if not (clean_url.startswith("https://") or clean_url.startswith("http://")):
            raise Exception("URL must start with http:// or https://")
        if len(clean_url) < 12:
            raise Exception("URL is too short")
        return clean_url

    def _format_http_response(self, resp_obj: typing.Any) -> str:
        code = getattr(resp_obj, "status_code", None)
        if code is None:
            code = getattr(resp_obj, "status", None)
        content = getattr(resp_obj, "body", resp_obj)
        if isinstance(content, (bytes, bytearray)):
            text_data = content.decode("utf-8", errors="replace")
        else:
            text_data = str(content)
        return "status=" + str(code) + chr(10) + text_data

    def _extract_main_body(self, raw_fetch: str) -> typing.Optional[str]:
        if not raw_fetch:
            return None
        first_line, _, remainder = raw_fetch.partition(chr(10))
        if not first_line.startswith("status="):
            return None
        code_val = first_line[len("status=") :].strip()
        if code_val == "EXCEPTION":
            return None
        if code_val.isdigit() and int(code_val) >= 400:
            return None
        return remainder

    def _is_valid_content(self, raw_fetch: str) -> bool:
        content_body = self._extract_main_body(raw_fetch)
        if content_body is None:
            return False
        clean_body = content_body.strip()
        if len(clean_body) < 20:
            return False
        text_lower = clean_body.lower()
        
        if '"message":"not found"' in text_lower.replace(" ", ""):
            return False
        if text_lower.startswith("<!doctype html>") and "404" in text_lower[:500]:
            if "not found" in text_lower and len(clean_body) < 800:
                return False
        if "could not find" in text_lower and len(clean_body) < 200:
            return False
        return True

    def _prepare_llm_text(self, raw_fetch: str) -> str:
        content_body = self._extract_main_body(raw_fetch)
        if content_body is None:
            return ""
        
        words = content_body.split()
        compressed_text = " ".join(words)
        char_limit = 10000
        if len(compressed_text) <= char_limit:
            return compressed_text
        cut_chars = len(compressed_text) - char_limit
        return compressed_text[:char_limit] + " [+" + str(cut_chars) + " chars omitted]"

    def _extract_final_status(self, raw_verdict: str) -> str:
        normalized = raw_verdict.strip().upper()
        top_line = normalized.split(chr(10), 1)[0]
        for tag, state_name in (
            ("UNVERIFIABLE", "unverifiable"),
            ("NOT_ATTESTED", "not_attested"),
            ("ATTESTED", "attested"),
        ):
            if tag in top_line:
                return state_name
        
        text_lower = raw_verdict.strip().lower()
        if "unverifiable" in text_lower:
            return "unverifiable"
        if "not_attested" in text_lower or "not attested" in text_lower:
            return "not_attested"
        if "attested" in text_lower:
            return "attested"
        return "unverifiable"

    @gl.public.write
    def create_fact_check(
        self,
        task_id: str,
        target_link: str,
        statement: str,
    ) -> None:
        if task_id in self.check_tasks:
            raise Exception("Task ID already exists: " + task_id)
        valid_url = self._verify_url_format(target_link)
        clean_statement = statement.strip()
        if len(clean_statement) < 8:
            raise Exception("Statement must be a clear factual sentence")
            
        self.check_tasks[task_id] = FactCheckRecord(
            initiator=str(gl.message.sender_address),
            target_link=valid_url,
            statement=clean_statement,
            current_state="pending",
            decision_rationale="",
            page_excerpt="",
        )

    @gl.public.write
    def execute_fact_check(self, task_id: str) -> None:
        task_record = self._get_task(task_id)
        if task_record.current_state != "pending":
            raise Exception(
                "Execution only valid for pending tasks, got: "
                + task_record.current_state
            )

        link = task_record.target_link
        stmt = task_record.statement

        def perform_web_request() -> str:
            try:
                web_resp = gl.nondet.web.get(link)
                return self._format_http_response(web_resp)
            except Exception as e:
                return "status=EXCEPTION" + chr(10) + type(e).__name__ + ": " + str(e)

        downloaded_data = gl.eq_principle.strict_eq(perform_web_request)

        if not self._is_valid_content(downloaded_data):
            task_record.current_state = "unverifiable"
            task_record.page_excerpt = (
                "SOURCE=" + link + chr(10) + downloaded_data[:1200]
            )
            task_record.decision_rationale = (
                "UNVERIFIABLE: The contract failed to retrieve usable text from the URL. "
                "No independent verification possible. Raw dump follows:\n"
                + downloaded_data[:1500]
            )
            return

        usable_text = self._prepare_llm_text(downloaded_data)
        if not usable_text:
            task_record.current_state = "unverifiable"
            task_record.page_excerpt = "SOURCE=" + link + chr(10) + downloaded_data[:1200]
            task_record.decision_rationale = (
                "UNVERIFIABLE: Fetched data could not be parsed into readable evidence."
            )
            return

        task_record.page_excerpt = (
            "SOURCE=" + link + chr(10)
            + "TEXT_LEN=" + str(len(usable_text)) + chr(10)
            + usable_text[:1400]
        )

        def evaluate_claim() -> str:
            ai_prompt = (
                "You are an on-chain Fact Checker. Decide if the STATEMENT is "
                "supported by the PROVIDED WEB TEXT.\n\n"
                "Rules:\n"
                "1. Base decision ONLY on the text below.\n"
                "2. ATTESTED — the text supports the statement.\n"
                "3. NOT_ATTESTED — the text does not support or contradicts it.\n"
                "4. UNVERIFIABLE — the text is irrelevant, empty, or broken.\n"
                "5. Provide a short quote from the text in your reasoning.\n\n"
                "STATEMENT:\n" + stmt + "\n\n"
                "PROVIDED WEB TEXT:\n" + usable_text + "\n\n"
                "Respond with ATTESTED, NOT_ATTESTED, or UNVERIFIABLE on the first line, "
                "followed by your explanation."
            )
            return gl.nondet.exec_prompt(ai_prompt)

        final_verdict = gl.eq_principle.prompt_comparative(
            evaluate_claim,
            principle=(
                "The first line must be exactly ATTESTED, NOT_ATTESTED, or UNVERIFIABLE. "
                "The explanation text may vary."
            ),
        )

        task_record.decision_rationale = (
            "SOURCE=" + link + chr(10)
            + "TEXT_LEN=" + str(len(usable_text)) + chr(10)
            + final_verdict
        )
        task_record.current_state = self._extract_final_status(final_verdict)

    @gl.public.view
    def get_task_details(self, task_id: str) -> typing.Any:
        task_record = self._get_task(task_id)
        return {
            "initiator": task_record.initiator,
            "target_link": task_record.target_link,
            "statement": task_record.statement,
            "current_state": task_record.current_state,
            "decision_rationale": task_record.decision_rationale,
            "page_excerpt": task_record.page_excerpt,
        }