"""Prompt text. The system prompt is written from the schema and generic contract rules only."""

import hashlib

TOOL_NAME = "report_changes"
TOOL_DESCRIPTION = "Report the substantive changes between the sent and the signed version of the contract."

SYSTEM_PROMPT = """You compare two versions of a commercial contract. The SENT version was issued by the seller, \
the party that provides the services. The SIGNED version is the final negotiated text. Report every substantive \
change between them by calling the report_changes tool exactly once. Do not answer in text.

Rules:
1. Work clause by clause. Every clause has a heading. Report at most one item per clause. Use the clause_type \
that matches the clause; use "other" only for a clause that fits none of the listed types.
2. change: "added" when the heading exists only in the signed version. "removed" when the heading exists only in \
the sent version. "modified" when the heading exists in both versions and the substance differs. A right, duty, \
limit or number added or dropped inside an existing clause makes that clause "modified".
3. A change is substantive when it alters a number, a period, a percentage, a right, an obligation, a limit, a \
party or a legal place. Ignore cosmetic edits: numbers written as words versus digits, "shall" versus "will", \
a different order of clauses, a different effective date, different signatory names or titles, punctuation and \
formatting. Do not report a clause whose substance is the same in both versions.
4. direction is judged from the seller's side. "buyer-favorable": the change gives the buyer more rights, \
less cost or less risk. "seller-favorable": the reverse. "neutral": neither side gains. Guide by clause type: \
payment_terms: a longer payment period favors the buyer. price_discount: a larger discount favors the buyer. \
liability_cap: a higher cap on the seller's liability favors the buyer. auto_renewal: removing automatic \
renewal favors the buyer. termination: a new right for the buyer to terminate favors the buyer. sla: a higher \
uptime commitment or added service credits favor the buyer, a lower uptime commitment favors the seller. \
data_processing: added data protection duties for the seller favor the buyer. confidentiality: a longer or \
broader duty favors the party that is protected, usually the buyer. governing_law: neutral unless one party \
clearly gains. warranty: a longer or broader warranty favors the buyer.
5. summary is one short sentence. sent_excerpt and signed_excerpt are short exact quotes (at most 25 words) \
from the respective version that show the change. Use an empty string for the side where the clause does not exist.
6. If there are no substantive changes, call the tool with an empty changes list."""

SYSTEM_PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()

USER_TEMPLATE = """<sent_version>
{sent}
</sent_version>

<signed_version>
{signed}
</signed_version>

Report the substantive changes between the sent and the signed version."""

RETRY_SCHEMA_TEMPLATE = "The tool input was rejected: {error}\nCall the tool again with a corrected input."
RETRY_NO_TOOL_MESSAGE = "Answer by calling the report_changes tool. Do not reply with text."


def build_user_message(sent: str, signed: str) -> str:
    return USER_TEMPLATE.format(sent=sent, signed=signed)
