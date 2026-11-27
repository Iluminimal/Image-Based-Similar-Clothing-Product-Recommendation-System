"use client";

/**
 * Сагсны өгөгдөл ба үйлдлүүд (TanStack Query). Товч дармагц дэлгэц тэр даруй өөрчлөгдөж, сервер
 * татгалзвал буцна.
 */

import { useUserMessage } from "@/lib/api/use-user-message";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/features/auth/auth-store";
import { queryKeys } from "@/lib/query-keys";
import {
  addCartItem,
  fetchCart,
  removeCartItem,
  updateCartItem,
  type Cart,
  type NewCartItem,
} from "./cart-api";
import { withoutLine, withQuantity } from "./cart-math";

const mutationKey = ["cart", "mutation"] as const;

/** Сагс хэрэглэгчийнх, зочны хувьд browser-ийнх: cache-д тусдаа хадгална. */
function useCartKey() {
  const userId = useAuth((state) => state.user?.id);
  return [...queryKeys.cart, userId ?? "guest"] as const;
}

export function useCart() {
  const status = useAuth((state) => state.status);
  return useQuery({
    queryKey: useCartKey(),
    queryFn: fetchCart,
    // Session сэргэж дуусахаас өмнө хүсэлт явуулбал сервер зочны сагсыг буцаана.
    enabled: status !== "unknown",
    staleTime: 15_000,
  });
}

/**
 * Дэлгэцийг тэр даруй өөрчилдөг (optimistic) сагсны mutation. Сервер татгалзвал toast харуулж, буцаана.
 * Хурдан товшилтууд давхцдаг тул сервер рүү явсан сүүлчийн хүсэлт дууссаны дараа л хариуг нь хүлээн
 * зөвшөөрнө.
 */
function useCartMutation<Variables>(
  mutationFn: (variables: Variables) => Promise<Cart>,
  optimistic?: (cart: Cart, variables: Variables) => Cart,
) {
  const queryClient = useQueryClient();
  const message = useUserMessage();
  const key = useCartKey();
  const lastOne = () => queryClient.isMutating({ mutationKey }) <= 1;

  return useMutation({
    mutationKey,
    mutationFn,
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<Cart>(key);
      if (previous && optimistic) queryClient.setQueryData(key, optimistic(previous, variables));
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
      toast.error(message(error));
    },
    onSuccess: (cart) => {
      if (lastOne()) queryClient.setQueryData(key, cart);
    },
    onSettled: () => {
      if (lastOne()) void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

export function useAddToCart() {
  return useCartMutation(addCartItem, (cart, item: NewCartItem) => ({
    ...cart,
    item_count: cart.item_count + (item.quantity ?? 1), // badge шууд хөдөлнэ; мөрүүд серверээс ирнэ
  }));
}

export function useSetQuantity() {
  return useCartMutation(
    ({ itemId, quantity }: { itemId: number; quantity: number }) => updateCartItem(itemId, quantity),
    (cart, { itemId, quantity }) => withQuantity(cart, itemId, quantity),
  );
}

export function useRemoveItem() {
  return useCartMutation((itemId: number) => removeCartItem(itemId), withoutLine);
}
