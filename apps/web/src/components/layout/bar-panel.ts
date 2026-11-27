import { useEffect } from "react";

let open = 0;

/**
 * `isOpen` үнэн байх хугацаанд <html> дээр `data-bar-panel` attribute тавьж, цэс, хайлт эсвэл Bag нээлттэйг
 * хуудсанд мэдэгдэнэ. Тэр үед apple.com-ийн утасны bar шиг CSS хаах товчноос бусад бүгдийг бүдгэрүүлнэ
 * (globals.css дахь `.phone-bar-item`-ийг үзнэ үү). Энэ нь зөвхөн true/false биш, тоолуур: нэг хуудас
 * нээгдэж, нөгөө нь хаагдахад attribute арилах ёсгүй.
 */
export function useBarPanel(isOpen: boolean) {
  useEffect(() => {
    if (!isOpen) return;
    open += 1;
    document.documentElement.dataset.barPanel = "";
    return () => {
      open -= 1;
      if (open === 0) delete document.documentElement.dataset.barPanel;
    };
  }, [isOpen]);
}
