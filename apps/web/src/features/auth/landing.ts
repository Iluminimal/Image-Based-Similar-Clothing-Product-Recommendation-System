import { staffHome } from "./roles";

/** `/account` болон худалдан авагчийн дэд хуудсууд (`/account/profile`-оос бусад). */
const SHOPPER_ACCOUNT = /^\/account(?!\/profile)(\/|\?|#|$)/;

/**
 * Дөнгөж нэвтэрсэн хүнийг хаашаа явуулах вэ. Тодорхой хуудас хүсээгүй ажилтан (очих газар нь нүүр
 * хуудас) өөрийн нүүр рүү орно: админ самбар руу, агуулахын ажилтан бараа руу; бусад нь, мөн тодорхой
 * хуудас хүссэн хүн хүссэн газраа очно. Ажилтанд бүртгэлийн хэсгээс зөвхөн профайл бий тул шууд тийш
 * явуулна: эхлээд очоод дахин шилжвэл (`/account` -> `/account/orders` -> профайл) шилжилтүүд мөргөлдөж
 * хуудас хоосон үлдэж болдог.
 */
export function landingPath(next: string, role: string | undefined) {
  const home = staffHome(role);
  if (home && SHOPPER_ACCOUNT.test(next)) return "/account/profile";
  return (next === "/" && home) || next;
}
