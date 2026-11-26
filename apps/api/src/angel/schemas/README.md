# `schemas`: хүсэлт ба хариуны хэлбэр

Pydantic model-ууд. Эндээс OpenAPI schema, түүнээс вэбийн TypeScript төрөл үүсдэг.

- ORM model-оос тусдаа байна: client-д зөвхөн энд зарласан талбар харагдана.
- Оролтын хязгаарыг (урт, тооны муж) энд зааж, дүрмийг `services/`-д шалгана.
- **Өөрчилсний дараа `make api-types`** ажиллуулж, `apps/web/src/lib/api/schema.d.ts`-ийг commit хийнэ.
  Класс, route-ийн docstring ч тэр файлд ордог.
