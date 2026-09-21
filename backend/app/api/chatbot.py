from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.schemas.chatbot_schema import (
    ChatbotContextRequest,
    ChatbotContextResponse,
    SupportedChatbotQuestionsResponse,
)
from app.services.chatbot_service import (
    build_chatbot_context,
    supported_chatbot_questions,
)

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
