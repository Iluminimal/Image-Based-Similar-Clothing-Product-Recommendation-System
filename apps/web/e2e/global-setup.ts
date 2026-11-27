import { spawnSync } from "node:child_process";
import path from "node:path";
import { ADMIN_EMAIL, ADMIN_PASSWORD, WAREHOUSE_EMAIL, WAREHOUSE_PASSWORD } from "./support/env";

/**
 * Админ тестүүд нэвтрэх админ, агуулахын ажилтныг бэлдэнэ. Оператор ашигладаг CLI-г (`make create-admin`,
 * `make create-warehouse`) дууддаг тул тэр замыг ч шалгана. Дахин дахин ажиллуулахад аюулгүй: байгаа
 * account-д тэр role-ийг өгч, энэ нууц үгийг тавина.
 */
function provision(command: "create-admin" | "create-warehouse", email: string, name: string, password: string) {
  const result = spawnSync("uv", ["run", "python", "-m", "angel.cli.admin", command, "--email", email, "--name", name], {
    cwd: path.resolve(__dirname, "../../api"),
    env: { ...process.env, ADMIN_PASSWORD: password },
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`Could not run ${command} for the e2e account ${email}:\n${result.stdout}\n${result.stderr}`);
  }
}

export default function globalSetup() {
  provision("create-admin", ADMIN_EMAIL, "E2E Admin", ADMIN_PASSWORD);
  provision("create-warehouse", WAREHOUSE_EMAIL, "E2E Warehouse", WAREHOUSE_PASSWORD);
}
