from __future__ import annotations

from typing import Any, Optional


class ExceptionTaggingService:
    def build_tagged_cells(
        self,
        *,
        exception_id: str,
        addresses: list[str],
        tagged_cells: list[dict[str, Any]],
        sheet_name: str,
        workbook_name: Optional[str],
    ) -> list[dict[str, Any]]:
        normalized_sheet = str(sheet_name or "").strip()
        if not normalized_sheet:
            raise ValueError("sheet_name is required")

        tagged_cells_from_payload: list[dict[str, Any]] = []
        for item in tagged_cells or []:
            if not isinstance(item, dict):
                continue
            address = str(item.get("address") or "").strip().upper()
            if not address:
                continue
            tagged_cells_from_payload.append(
                {
                    "address": address,
                    "exception_id": exception_id,
                    "comment": str(item.get("comment") or f"Exception tagged: {exception_id}").strip(),
                    "fill_color": str(item.get("fill_color") or item.get("fillColor") or "#dbeafe").strip() or "#dbeafe",
                    "previous_fill_color": str(item.get("previous_fill_color") or item.get("previousFillColor") or "").strip(),
                    "sheet_name": str(item.get("sheet_name") or item.get("sheetName") or normalized_sheet).strip(),
                    "workbook_name": str(item.get("workbook_name") or item.get("workbookName") or workbook_name or "").strip(),
                    "tagged_at": str(item.get("tagged_at") or item.get("taggedAt") or "").strip(),
                }
            )

        fallback_tagged_cells = [
            {
                "address": str(address or "").strip().upper(),
                "exception_id": exception_id,
                "comment": f"Exception tagged: {exception_id}",
                "fill_color": "#dbeafe",
                "previous_fill_color": "",
                "sheet_name": normalized_sheet,
                "workbook_name": workbook_name,
            }
            for address in addresses
            if str(address or "").strip()
        ]

        final_cells = tagged_cells_from_payload or fallback_tagged_cells
        if not final_cells:
            raise ValueError("At least one address is required")
        return final_cells


exception_tagging_service = ExceptionTaggingService()
