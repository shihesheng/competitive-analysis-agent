"""产品规格事实底座的只读接口：搜索 / 列表 / 详情 / 对比。

与 /api/analysis/* 分析主流程完全解耦，挂载在独立的 APIRouter 上，
不触碰 workflow，也不会影响现有任何接口。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import product_catalog_service as catalog

router = APIRouter(prefix="/api/products", tags=["products"])


class CompareRequest(BaseModel):
    category: str = Field(default="gaming_mouse", description="品类，如 gaming_mouse")
    product_a: str = Field(..., description="产品 A 查询（id/型号/简称均可），如 GPX2")
    product_b: str = Field(..., description="产品 B 查询，如 Viper V3 Pro")


# 注意：静态路径（/search、/compare）必须声明在动态 /{category} 之前，避免被吞掉。
@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=1, description="搜索词，匹配 id/brand/model/aliases/community_aliases/family"),
    category: str = Query("gaming_mouse", description="品类"),
):
    try:
        detailed = catalog.search_products_detailed(category, q)
    except catalog.CategoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "query": q,
        "normalized_query": catalog.normalize(q),
        "category": category,
        "count": detailed["count"],
        "needs_disambiguation": detailed["needs_disambiguation"],
        "disambiguation_reason": detailed["disambiguation_reason"],
        "results": detailed["results"],
    }


@router.post("/compare")
async def compare_products(req: CompareRequest):
    try:
        return catalog.compare_products(req.category, req.product_a, req.product_b)
    except catalog.CategoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except catalog.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/categories")
async def list_categories():
    return {"categories": catalog.available_categories()}


@router.get("/{category}")
async def list_category(category: str):
    try:
        data = catalog.load_catalog(category)
    except catalog.CategoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    products = data.get("products", [])
    return {
        "category": category,
        "category_label": data.get("category_label"),
        "updated_at": data.get("updated_at"),
        "count": len(products),
        "products": products,
    }


@router.get("/{category}/{product_id}")
async def product_detail(category: str, product_id: str):
    try:
        product, matched_by, matched_value = catalog.resolve_product(category, product_id)
    except catalog.CategoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except catalog.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "category": category,
        "matched_by": matched_by,
        "matched_value": matched_value,
        "product": product,
    }
