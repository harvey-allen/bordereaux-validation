from __future__ import annotations

from typing import Optional

from app.schemas.rules_engine import RulesEngineResponse, RulesEngineRule
from app.testpacks.core import TEST_PACKS, BaseTestPack, normalize_pack_name


class RulesEngineService:
    def get_rules(self, test_pack: Optional[str] = None) -> RulesEngineResponse:
        requested_pack = normalize_pack_name(test_pack)
        available_packs = sorted(TEST_PACKS.keys())

        if requested_pack:
            if requested_pack not in TEST_PACKS:
                raise ValueError(f"Unknown test pack '{requested_pack}'")
            packs_to_scan = [requested_pack]
        else:
            packs_to_scan = available_packs

        rules: list[RulesEngineRule] = []
        signature_to_rule_index: dict[tuple[str, str, str, str, Optional[str]], int] = {}

        for pack_name in packs_to_scan:
            pack_cls = TEST_PACKS.get(pack_name)
            if pack_cls is None or not issubclass(pack_cls, BaseTestPack):
                continue

            for metadata in pack_cls.collect_registered_tests():
                severity_name = metadata.severity.name
                test_type_name = metadata.test_type.name if metadata.test_type else None

                for target_column in metadata.target_columns:
                    signature = (
                        metadata.rule_id,
                        str(target_column),
                        metadata.description,
                        severity_name,
                        test_type_name,
                    )

                    if not requested_pack and signature in signature_to_rule_index:
                        rule_index = signature_to_rule_index[signature]
                        current_packs = {p.strip() for p in rules[rule_index].pack.split(",") if p.strip()}
                        current_packs.add(pack_name)
                        rules[rule_index].pack = ", ".join(sorted(current_packs))
                        continue

                    rules.append(
                        RulesEngineRule(
                            pack=pack_name,
                            rule_id=metadata.rule_id,
                            target_column=str(target_column),
                            description=metadata.description,
                            severity=severity_name,
                            test_type=test_type_name,
                        )
                    )
                    if not requested_pack:
                        signature_to_rule_index[signature] = len(rules) - 1

        rules.sort(key=lambda item: (item.target_column.lower(), item.rule_id.lower(), item.pack.lower()))
        return RulesEngineResponse(packs=available_packs, rules=rules)


rules_engine_service = RulesEngineService()
