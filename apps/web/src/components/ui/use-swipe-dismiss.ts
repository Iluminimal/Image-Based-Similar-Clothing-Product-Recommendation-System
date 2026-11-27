"use client";

import { useRef, type PointerEvent } from "react";

const THRESHOLD = 110; // пиксель
const FLICK = 0.6; // пиксель/мс

/**
 * Panel-ийг хуруугаар чирж хаана: баруун талын drawer, доод sheet. Зөвхөн touch дээр (хулганад хаах товч
 * бий). Хуруу `axis` чиглэлд хөндлөн чиглэлээс илүү хөдөлсөн үед л ажиллана, ингэснээр доторх жагсаалтыг
 * scroll хийж болсоор байна. Panel хурууг дагана. Тодорхой зайнаас цааш чирэх эсвэл хурдан шудрахад
 * `onDismiss` ажиллана, үгүй бол panel байрандаа буцна. `handle` (CSS selector) өгвөл зөвхөн тэр хэсгээс
 * эхэлсэн чирэлт panel-ийг хөдөлгөнө, доорх scroll хийдэг агуулгыг хөндөхгүй.
 */
export function useSwipeDismiss(axis: "x" | "y", onDismiss: () => void, handle?: string) {
  const drag = useRef<{ x: number; y: number; at: number; active: boolean; last: number } | null>(null);

  function follow(element: HTMLElement, distance: number, animated: boolean) {
    element.style.transition = animated ? "translate 350ms var(--ease-out-expo)" : "none";
    element.style.translate = distance === 0 ? "" : axis === "x" ? `${distance}px 0` : `0 ${distance}px`;
  }

  return {
    onPointerDown(event: PointerEvent<HTMLElement>) {
      if (event.pointerType !== "touch") return;
      if (handle && !(event.target as Element).closest(handle)) return;
      drag.current = { x: event.clientX, y: event.clientY, at: performance.now(), active: false, last: 0 };
    },
    onPointerMove(event: PointerEvent<HTMLElement>) {
      const start = drag.current;
      if (!start) return;
      const along = axis === "x" ? event.clientX - start.x : event.clientY - start.y;
      const across = axis === "x" ? event.clientY - start.y : event.clientX - start.x;
      if (!start.active) {
        if (Math.abs(across) > Math.abs(along) && Math.abs(across) > 8) {
          drag.current = null; // нөгөө чиглэлд scroll хийж байна
          return;
        }
        if (along < 8) return;
        start.active = true;
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }
      start.last = Math.max(0, along);
      follow(event.currentTarget, start.last, false);
    },
    onPointerUp(event: PointerEvent<HTMLElement>) {
      const start = drag.current;
      drag.current = null;
      if (!start?.active) return;
      const speed = start.last / Math.max(1, performance.now() - start.at);
      if (start.last > THRESHOLD || speed > FLICK) onDismiss();
      else follow(event.currentTarget, 0, true);
    },
    onPointerCancel(event: PointerEvent<HTMLElement>) {
      if (drag.current?.active) follow(event.currentTarget, 0, true);
      drag.current = null;
    },
  };
}
