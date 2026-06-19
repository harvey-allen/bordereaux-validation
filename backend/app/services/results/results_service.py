from __future__ import annotations

from typing import Any, Optional

from app.schemas.results import PreviousVersionSummary, VersionComparisonResponse, VersionKpiSummary, VersionTrendPoint


class ResultsDomainService:
    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def build_version_kpis(self, results_json: dict[str, Any]) -> VersionKpiSummary:
        kpis_from_json = results_json.get("KPIs") if isinstance(results_json, dict) else {}
        if not isinstance(kpis_from_json, dict):
            kpis_from_json = {}

        summary_metrics = results_json.get("summary_metrics") if isinstance(results_json, dict) else {}
        if not isinstance(summary_metrics, dict):
            summary_metrics = {}

        failed_items = results_json.get("failed") if isinstance(results_json, dict) else []
        failed_items = failed_items if isinstance(failed_items, list) else []
        passed_tests = results_json.get("passed_tests") if isinstance(results_json, dict) else []
        passed_tests = passed_tests if isinstance(passed_tests, list) else []
        passed_umrs = results_json.get("passed_umrs") if isinstance(results_json, dict) else []
        passed_umrs = passed_umrs if isinstance(passed_umrs, list) else []

        failed_submission_ids: set[str] = set()
        failed_test_ids: set[str] = set()
        for item in failed_items:
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id") or item.get("umr") or "").strip()
            if row_id:
                failed_submission_ids.add(row_id)
            for test_id in (item.get("tests") or []):
                text_id = str(test_id or "").strip()
                if text_id:
                    failed_test_ids.add(text_id)

        submissions_failed = len(failed_submission_ids)
        tests_failed = len(failed_test_ids)

        submissions_failed = self._to_int(kpis_from_json.get("submissions_failed")) if kpis_from_json else submissions_failed
        if submissions_failed is None:
            submissions_failed = len(failed_submission_ids)

        tests_failed = self._to_int(kpis_from_json.get("tests_failed")) if kpis_from_json else tests_failed
        if tests_failed is None:
            tests_failed = len(failed_test_ids)

        total_submissions = self._to_int(kpis_from_json.get("total_submissions"))
        if total_submissions is None:
            total_submissions = self._to_int(summary_metrics.get("total_submissions"))
        if total_submissions is None:
            total_submissions = len(failed_submission_ids.union({str(v).strip() for v in passed_umrs if str(v).strip()}))

        total_tests = self._to_int(kpis_from_json.get("total_tests"))
        if total_tests is None:
            total_tests = self._to_int(summary_metrics.get("total_tests"))
        if total_tests is None:
            total_tests = len(failed_test_ids.union({str(v).strip() for v in passed_tests if str(v).strip()}))

        submissions_failed_pct = self._to_float(kpis_from_json.get("submissions_failed_pct"))
        if submissions_failed_pct is None:
            submissions_failed_pct = ((submissions_failed / total_submissions) * 100) if total_submissions else None

        tests_failed_pct = self._to_float(kpis_from_json.get("tests_failed_pct"))
        if tests_failed_pct is None:
            tests_failed_pct = ((tests_failed / total_tests) * 100) if total_tests else None

        tests_passed_pct = self._to_float(kpis_from_json.get("tests_passed_pct"))
        if tests_passed_pct is None:
            tests_passed_pct = ((1 - (tests_failed / total_tests)) * 100) if total_tests else None

        fields_failed = self._to_int(kpis_from_json.get("fields_failed"))
        if fields_failed is None:
            fields_failed = self._to_int(summary_metrics.get("fields_failed"))

        total_fields = self._to_int(kpis_from_json.get("total_fields"))
        if total_fields is None:
            total_fields = self._to_int(summary_metrics.get("total_fields"))

        fields_failed_pct = self._to_float(kpis_from_json.get("fields_failed_pct"))
        if fields_failed_pct is None:
            fields_failed_pct = ((fields_failed / total_fields) * 100) if fields_failed is not None and total_fields else None

        return VersionKpiSummary(
            submissions_failed=submissions_failed,
            submissions_failed_pct=submissions_failed_pct,
            fields_failed=fields_failed,
            fields_failed_pct=fields_failed_pct,
            tests_failed=tests_failed,
            tests_failed_pct=tests_failed_pct,
            tests_passed_pct=tests_passed_pct,
        )

    @staticmethod
    def resolve_version_name(version_obj: Any) -> Optional[str]:
        version_name = str(getattr(version_obj, "version_name", "") or "").strip() or None
        if version_name is None and isinstance(getattr(version_obj, "results_json", None), dict):
            version_name = str(version_obj.results_json.get("version_name") or "").strip() or None
        return version_name

    def build_version_comparison(
        self,
        *,
        saved_versions: list[Any],
        current_workbook: str,
        current_sheet: str,
    ) -> VersionComparisonResponse:
        trend_items: list[VersionTrendPoint] = []
        previous_version: Optional[PreviousVersionSummary] = None

        for item in sorted(saved_versions, key=lambda v: v.version.created_at):
            kpis = self.build_version_kpis(dict(item.version.results_json or {}))
            trend_items.append(
                VersionTrendPoint(
                    id=item.version.id,
                    workbook_name=item.workbook_name,
                    sheet_name=item.sheet_name,
                    created_at=item.version.created_at.isoformat(),
                    updated_at=item.version.updated_at.isoformat(),
                    version_name=self.resolve_version_name(item.version),
                    test_passed_pct=kpis.tests_passed_pct,
                    submissions_failed_pct=kpis.submissions_failed_pct,
                    fields_failed_pct=kpis.fields_failed_pct,
                )
            )

        for item in saved_versions:
            same_scope = item.workbook_name == current_workbook and item.sheet_name == current_sheet
            if same_scope:
                continue

            kpis = self.build_version_kpis(dict(item.version.results_json or {}))
            previous_version = PreviousVersionSummary(
                id=item.version.id,
                workbook_name=item.workbook_name,
                sheet_name=item.sheet_name,
                created_at=item.version.created_at.isoformat(),
                updated_at=item.version.updated_at.isoformat(),
                version_name=self.resolve_version_name(item.version),
                kpis=kpis,
            )
            break

        return VersionComparisonResponse(previous_version=previous_version, trend=trend_items)


results_domain_service = ResultsDomainService()
