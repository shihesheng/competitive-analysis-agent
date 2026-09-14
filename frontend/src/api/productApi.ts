import { apiGet, apiPost } from "./client";
import type {
  ProductCatalog,
  ProductCategoriesResponse,
  ProductCompareResponse,
  ProductDetailResponse,
  ProductSearchResponse,
} from "../types/product";

export const DEFAULT_PRODUCT_CATEGORY = "gaming_mouse";

export const productApi = {
  // GET /api/products/search?q=&category=
  searchProducts: (q: string, category: string = DEFAULT_PRODUCT_CATEGORY) =>
    apiGet<ProductSearchResponse>(
      `/api/products/search?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`,
    ),

  // GET /api/products/{category}/{product_id}
  getProduct: (category: string, productId: string) =>
    apiGet<ProductDetailResponse>(
      `/api/products/${encodeURIComponent(category)}/${encodeURIComponent(productId)}`,
    ),

  // POST /api/products/compare
  compareProducts: (category: string, productA: string, productB: string) =>
    apiPost<ProductCompareResponse>("/api/products/compare", {
      category,
      product_a: productA,
      product_b: productB,
    }),

  // GET /api/products/{category}
  listCategory: (category: string = DEFAULT_PRODUCT_CATEGORY) =>
    apiGet<ProductCatalog>(`/api/products/${encodeURIComponent(category)}`),

  // GET /api/products/categories
  getCategories: () =>
    apiGet<ProductCategoriesResponse>("/api/products/categories"),
};
