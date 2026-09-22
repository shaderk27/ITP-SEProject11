from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.schemas.chatbot_schema import (
    ChatbotAskRequest,
    ChatbotAskResponse,
    ChatbotContextRequest,
    ChatbotContextResponse,
    SupportedChatbotQuestionsResponse,
)
from app.services.chatbot_answer_service import answer_question
from app.services.chatbot_service import (
    build_chatbot_context,
    supported_chatbot_questions,
)
from app.services.llm_client import LLMUnavailableError

router = APIRouter(prefix="/api/chatbot", tags=["Chatbot"])


@router.get("/supported-questions", response_model=SupportedChatbotQuestionsResponse)
def get_supported_questions() -> SupportedChatbotQuestionsResponse:
    return supported_chatbot_questions()


@router.post("/query-context", response_model=ChatbotContextResponse)
def get_query_context(
    request: ChatbotContextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatbotContextResponse:
    try:
        return build_chatbot_context(db, current_user, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post("/ask", response_model=ChatbotAskResponse)
def ask(
    request: ChatbotAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatbotAskResponse:
    """Answer a free-text question from role-scoped data using the LLM.

    503 means the LLM is unavailable (no key, provider down); the widget then
    falls back to the rule-based answers built on /query-context.
    """
    try:
        return answer_question(db, current_user, request)
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
