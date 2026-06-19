from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Subscription, check_pack_access
from app.pack_config_service import pack_config_service
from app.testpacks.core import TEST_PACKS, get_pack_name_variants, normalize_pack_name
from app.schemas.validation import ValidateRequest


class ValidationOrchestrationService:
    async def build_effective_pack_configs(
        self,
        *,
        payload: ValidateRequest,
        subscription: Subscription,
        db_available: bool,
        db: AsyncSession | None,
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        normalized_test_packs: list[str] = []
        seen_packs: set[str] = set()
        for pack_name in payload.testPacks:
            normalized_pack_name = normalize_pack_name(pack_name)
            if not normalized_pack_name or normalized_pack_name in seen_packs:
                continue
            seen_packs.add(normalized_pack_name)
            normalized_test_packs.append(normalized_pack_name)

        normalized_pack_configs: dict[str, dict[str, Any]] = {}
        for pack_name, pack_config in (payload.packConfigs or {}).items():
            normalized_pack_name = normalize_pack_name(pack_name)
            if not normalized_pack_name:
                continue
            existing = dict(normalized_pack_configs.get(normalized_pack_name, {}))
            existing.update(dict(pack_config or {}))
            normalized_pack_configs[normalized_pack_name] = existing

        unknown_packs = [pack_name for pack_name in normalized_test_packs if pack_name not in TEST_PACKS]
        if unknown_packs:
            unique_unknown = ", ".join(sorted(set(unknown_packs)))
            raise ValueError(f"Unknown test pack(s): {unique_unknown}")

        if normalized_test_packs:
            check_pack_access(subscription, normalized_test_packs)

        effective_pack_configs = dict(normalized_pack_configs)

        if db_available and db is not None and not subscription.metadata.get("is_dev_key") and payload.sheetName:
            subscription_user_id = subscription.metadata.get("user_id")
            organisation_id = subscription.metadata.get("organisation_id")
            if subscription_user_id is not None and organisation_id is not None:
                for pack_name in normalized_test_packs:
                    stored_config = None
                    for variant in get_pack_name_variants(pack_name):
                        stored_config = await pack_config_service.get_config(
                            db,
                            organisation_id=int(organisation_id),
                            user_id=int(subscription_user_id),
                            workbook_name=payload.workbookName,
                            sheet_name=payload.sheetName,
                            test_pack=variant,
                        )
                        if stored_config is not None:
                            break

                    incoming_pack_config = normalized_pack_configs.get(pack_name, {})
                    if stored_config is None:
                        effective_pack_configs[pack_name] = dict(incoming_pack_config or {})
                    else:
                        merged_pack_config = dict(stored_config)
                        merged_pack_config.update(dict(incoming_pack_config or {}))
                        effective_pack_configs[pack_name] = merged_pack_config

                if normalized_pack_configs:
                    for pack_name, pack_config in normalized_pack_configs.items():
                        if pack_name not in normalized_test_packs:
                            continue
                        await pack_config_service.upsert_config(
                            db,
                            organisation_id=int(organisation_id),
                            user_id=int(subscription_user_id),
                            workbook_name=payload.workbookName,
                            sheet_name=payload.sheetName,
                            test_pack=pack_name,
                            pack_config=dict(pack_config or {}),
                        )

        return normalized_test_packs, effective_pack_configs


validation_orchestration_service = ValidationOrchestrationService()
