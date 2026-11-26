import { onlineManager } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "./query-client";

describe("createQueryClient", () => {
  afterEach(() => onlineManager.setOnline(true));

  it("tries a change at once while offline, so it fails in sight instead of being sent later", async () => {
    onlineManager.setOnline(false);
    const client = createQueryClient();
    const send = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    const mutation = client.getMutationCache().build(client, { mutationFn: send });

    await expect(mutation.execute(undefined)).rejects.toThrow("Failed to fetch");
    expect(send).toHaveBeenCalledOnce();
  });
});
