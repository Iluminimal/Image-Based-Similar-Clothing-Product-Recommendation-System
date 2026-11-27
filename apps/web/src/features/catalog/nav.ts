import type { components } from "@/lib/api/client";

export type CatalogNav = components["schemas"]["CatalogNav"];
export type NavDepartment = components["schemas"]["NavDepartment"];
export type NavNode = components["schemas"]["NavNode"];

/**
 * Header дээрх department-ууд. Хүсэлт явуулалгүй мэддэг тул холбоосууд хуудастайгаа хамт зурагдана (хайлтын
 * систем ч уншина). Тэдгээрийн доорх ангиллын цэсний өгөгдөл `GET /catalog/nav`-аас ирнэ.
 */
export const DEPARTMENT_LINKS = [
  { slug: "women", label: "Women" },
  { slug: "men", label: "Men" },
  { slug: "kids", label: "Kids" },
] as const;

/** `/c/men`, `/c/men/apparel/topwear/tshirts`. Node-ын `path` бол department-ийн дараах хэсэг. */
export function categoryHref(department: string, path?: string): string {
  return path ? `/c/${department}/${path}` : `/c/${department}`;
}

export type CategoryTrail = {
  department: NavDepartment;
  /** Бүлэг, дэд ангилал, article type: URL хэр гүн явна тэр хэмжээнд. */
  nodes: NavNode[];
};

/**
 * URL-ын хэсгүүдийг nav-тай тулгана. Nav-д байхгүй бол (бараагүй ангилал ч мөн) `null` буцаана: хуучирсан
 * холбоос хоосон хуудас биш, 404 болно.
 */
export function findTrail(nav: CatalogNav, departmentSlug: string, segments: string[] = []): CategoryTrail | null {
  const department = nav.departments.find((d) => d.slug === departmentSlug);
  if (!department) return null;
  const nodes: NavNode[] = [];
  let level = department.groups;
  for (const segment of segments) {
    const node = level.find((n) => n.slug === segment);
    if (!node) return null;
    nodes.push(node);
    level = node.children;
  }
  return { department, nodes };
}

/** Sitemap-д оруулах бүх URL: department болон доорх бүх node. */
export function categoryPaths(nav: CatalogNav): string[] {
  const out: string[] = [];
  const walk = (department: string, nodes: NavNode[]) => {
    for (const node of nodes) {
      out.push(categoryHref(department, node.path));
      walk(department, node.children);
    }
  };
  for (const department of nav.departments) {
    out.push(categoryHref(department.slug));
    walk(department.slug, department.groups);
  }
  return out;
}

/** Цэсний шуурхай холбоост зориулж department-ийн бүлгүүдийн хамгийн алдартай article type-ууд. */
export function popularTypes(department: NavDepartment, limit = 8): NavNode[] {
  return department.groups
    .flatMap((group) => group.children.flatMap((sub) => sub.children))
    .sort((a, b) => b.product_count - a.product_count)
    .slice(0, limit);
}

/**
 * Ангиллын хуудаснаас дараа нь хаашаа орж болох вэ. Хамгийн доод ангиллын (leaf) доор юу ч байхгүй тул
 * зэрэгцээ ангиллуудыг санал болгоно (энэ leaf өөрөө `ancestors`-оос хасагдана).
 */
export function drilldown(department: NavDepartment, nodes: NavNode[]) {
  const current = nodes.at(-1);
  const isLeaf = current !== undefined && current.children.length === 0;
  const ancestors = isLeaf ? nodes.slice(0, -1) : nodes;
  const parent = ancestors.at(-1);
  return { ancestors, options: parent ? parent.children : department.groups, current };
}

/**
 * Нэр нь текстийг агуулсан дэд ангилал, article type, том нь түрүүнд. Нэг нэр хэд хэдэн
 * department-д байж болно (Men, Women хоёрт "T-shirts"); тус бүр өөр үр дүн.
 */
export function matchCategories(nav: CatalogNav, text: string, limit: number): { department: NavDepartment; node: NavNode }[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return [];
  const hits: { department: NavDepartment; node: NavNode }[] = [];
  for (const department of nav.departments) {
    for (const group of department.groups) {
      for (const sub of group.children) {
        if (sub.name.toLowerCase().includes(needle)) hits.push({ department, node: sub });
        for (const leaf of sub.children) {
          if (leaf.name.toLowerCase().includes(needle)) hits.push({ department, node: leaf });
        }
      }
    }
  }
  return hits.sort((a, b) => b.node.product_count - a.node.product_count).slice(0, limit);
}
