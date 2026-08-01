"""API error mapping to a stable JSON problem shape."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from kelbet.domain.exceptions import (
    ActiveGenerationLimitError,
    AdminActionConflictError,
    AdminAuthorizationError,
    AssetNotFoundError,
    AuthError,
    CatalogModelNotFoundError,
    ChatMessageTooLongError,
    ChatProviderError,
    ConsentRequiredError,
    ExpiredInitDataError,
    GenerationConflictError,
    GenerationNotFoundError,
    GenerationTemplateNotFoundError,
    GenerationTemplateValidationError,
    IdempotencyConflictError,
    InsufficientCreditsError,
    InvalidGenerationTransitionError,
    InvalidInitDataError,
    InvalidQuoteParamsError,
    InvalidSessionError,
    KelbetError,
    ModelUnavailableError,
    ModerationDecisionNotFoundError,
    ModerationRateLimitError,
    ModerationRejectedError,
    PaymentOrderNotFoundError,
    PaymentProductNotFoundError,
    PaymentRefundConflictError,
    PaymentRefundNotFoundError,
    PaymentRefundUnavailableError,
    PaymentUnavailableError,
    PaymentValidationError,
    QuoteNotFoundError,
    RateLimitExceededError,
    ReplayInitDataError,
    StorageError,
    UploadValidationError,
    UserBlockedError,
    UserNotFoundError,
    WebhookVerificationError,
)


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or str(uuid4())


def error_body(
    *,
    code: str,
    message: str,
    correlation_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GenerationTemplateNotFoundError)
    async def _generation_template_not_found(
        request: Request, exc: GenerationTemplateNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="generation_template_not_found",
                message="Generation template is unavailable",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(GenerationTemplateValidationError)
    async def _generation_template_invalid(
        request: Request, exc: GenerationTemplateValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="generation_template_invalid",
                message=str(exc),
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ModerationDecisionNotFoundError)
    async def _moderation_decision_not_found(
        request: Request, exc: ModerationDecisionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="moderation_decision_not_found",
                message="Moderation decision not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ModerationRateLimitError)
    async def _moderation_rate_limited(
        request: Request, exc: ModerationRateLimitError
    ) -> JSONResponse:
        message = (
            "Қысқа уақытта тым көп сұрау жіберілді. Кредит шегерілмеді."
            if exc.language == "kk"
            else "Слишком много запросов за короткое время. Кредит не списан."
        )
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60"},
            content=error_body(
                code="moderation_rate_limited",
                message=message,
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ModerationRejectedError)
    async def _moderation_rejected(request: Request, exc: ModerationRejectedError) -> JSONResponse:
        message = (
            "Сұрау қауіпсіздік ережелері бойынша тоқтатылды. Кредит шегерілмеді."
            if exc.language == "kk"
            else "Запрос остановлен правилами безопасности. Кредит не списан."
        )
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="moderation_blocked",
                message=message,
                correlation_id=_correlation_id(request),
                details={"support_route": "/support"},
            ),
        )

    @app.exception_handler(ConsentRequiredError)
    async def _consent_required(request: Request, exc: ConsentRequiredError) -> JSONResponse:
        message = (
            "Фотодағы адамдардың құқықтары мен келісімін растаңыз."
            if exc.language == "kk"
            else "Подтвердите права на фото и согласие изображённых людей."
        )
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="photo_rights_consent_required",
                message=message,
                correlation_id=_correlation_id(request),
                details={"required_version": exc.required_version, "support_route": "/support"},
            ),
        )

    @app.exception_handler(AdminAuthorizationError)
    async def _admin_forbidden(request: Request, exc: AdminAuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_body(
                code="admin_forbidden",
                message="Operator permission required",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(AdminActionConflictError)
    async def _admin_conflict(request: Request, exc: AdminActionConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_body(
                code="admin_action_conflict",
                message="Operator action conflicts with current state",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(UserBlockedError)
    async def _user_blocked(request: Request, exc: UserBlockedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_body(
                code="user_blocked",
                message="Paid operations are blocked for this account",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(InvalidInitDataError)
    async def _invalid_init(request: Request, exc: InvalidInitDataError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body(
                code="invalid_init_data",
                message="Invalid Telegram initData",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ExpiredInitDataError)
    async def _expired_init(request: Request, exc: ExpiredInitDataError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body(
                code="expired_init_data",
                message="Telegram initData expired",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ReplayInitDataError)
    async def _replay(request: Request, exc: ReplayInitDataError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body(
                code="replay_init_data",
                message="Telegram initData already used",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(InvalidSessionError)
    async def _invalid_session(request: Request, exc: InvalidSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body(
                code="invalid_session",
                message="Authentication required",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(UserNotFoundError)
    async def _user_not_found(request: Request, exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="user_not_found",
                message="User not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(CatalogModelNotFoundError)
    async def _catalog_not_found(request: Request, exc: CatalogModelNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="model_not_found",
                message="Model not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ModelUnavailableError)
    async def _model_unavailable(request: Request, exc: ModelUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="model_unavailable",
                message="Model is unavailable",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(InvalidQuoteParamsError)
    async def _invalid_quote_params(request: Request, exc: InvalidQuoteParamsError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="invalid_quote_params",
                message="Invalid quote parameters",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(QuoteNotFoundError)
    async def _quote_not_found(request: Request, exc: QuoteNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="quote_not_found",
                message="Quote not found or expired",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(UploadValidationError)
    async def _upload_validation(request: Request, exc: UploadValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="upload_validation_error",
                message="Upload validation failed",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(AssetNotFoundError)
    async def _asset_not_found(request: Request, exc: AssetNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="asset_not_found",
                message="Asset not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(StorageError)
    async def _storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content=error_body(
                code="storage_error",
                message="Storage operation failed",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(GenerationNotFoundError)
    async def _generation_not_found(request: Request, exc: GenerationNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="generation_not_found",
                message="Generation not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(GenerationConflictError)
    async def _generation_conflict(request: Request, exc: GenerationConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_body(
                code="generation_conflict",
                message="Generation conflict",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(RateLimitExceededError)
    async def _rate_limited(request: Request, exc: RateLimitExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60"},
            content=error_body(
                code="rate_limited",
                message="Too many requests",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ActiveGenerationLimitError)
    async def _active_gen_limit(request: Request, exc: ActiveGenerationLimitError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=error_body(
                code="active_generation_limit",
                message="Too many active generations",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(InvalidGenerationTransitionError)
    async def _invalid_transition(
        request: Request, exc: InvalidGenerationTransitionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_body(
                code="invalid_generation_transition",
                message="Invalid generation transition",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(InsufficientCreditsError)
    async def _insufficient(request: Request, exc: InsufficientCreditsError) -> JSONResponse:
        return JSONResponse(
            status_code=402,
            content=error_body(
                code="insufficient_credits",
                message="Not enough credits",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ChatMessageTooLongError)
    async def _chat_too_long(request: Request, exc: ChatMessageTooLongError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="prompt_too_long",
                message="Prompt is too long",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(ChatProviderError)
    async def _chat_provider(request: Request, exc: ChatProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content=error_body(
                code="assistant_provider_error",
                message="Prompt assistant is temporarily unavailable",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(IdempotencyConflictError)
    async def _idempotency_conflict(
        request: Request, exc: IdempotencyConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_body(
                code="idempotency_conflict",
                message="Idempotency key was already used",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(AuthError)
    async def _auth(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body(
                code="auth_error",
                message="Authentication failed",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(WebhookVerificationError)
    async def _webhook_verification(
        request: Request, exc: WebhookVerificationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body(
                code="webhook_verification_failed",
                message="Webhook authenticity could not be verified",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentUnavailableError)
    async def _payment_unavailable(request: Request, exc: PaymentUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_body(
                code="payments_unavailable",
                message="Payments are temporarily unavailable",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentProductNotFoundError)
    async def _payment_product_not_found(
        request: Request, exc: PaymentProductNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="payment_product_not_found",
                message="Payment product not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentOrderNotFoundError)
    async def _payment_order_not_found(
        request: Request, exc: PaymentOrderNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="payment_order_not_found",
                message="Payment order not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentValidationError)
    async def _payment_validation(request: Request, exc: PaymentValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="payment_validation_error",
                message="Payment request could not be validated",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentRefundNotFoundError)
    async def _payment_refund_not_found(
        request: Request, exc: PaymentRefundNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body(
                code="payment_refund_not_found",
                message="Payment refund not found",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentRefundConflictError)
    async def _payment_refund_conflict(
        request: Request, exc: PaymentRefundConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_body(
                code="payment_refund_conflict",
                message="Payment refund conflicts with current state",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(PaymentRefundUnavailableError)
    async def _payment_refund_unavailable(
        request: Request, exc: PaymentRefundUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_body(
                code="payment_refunds_unavailable",
                message="Payment refunds are unavailable",
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(KelbetError)
    async def _domain(request: Request, exc: KelbetError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_body(
                code="domain_error",
                message="Request could not be processed",
                correlation_id=_correlation_id(request),
            ),
        )
