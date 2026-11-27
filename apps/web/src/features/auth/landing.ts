import { staffHome } from "./roles";

/** `/account` болон худалдан авагчийн дэд хуудсууд (`/account/profile`-оос бусад). */
const SHOPPER_ACCOUNT = /^\/account(?!\/profile)(\/|\?|#|$)/;

/**
 * Дөнгөж нэвтэрсэн хүнийг хаашаа явуулах вэ. Тодорхой хуудас хүсээгүй (очих газар нь нүүр хуудас) ажилтан
 * `/admin` руу орно: админ хянах самбар, агуулахын ажилтан илгээх самбар харна. Бусад хүн, мөн тодорхой
 * хуудас хүссэн хүн хүссэн газраа очно. Ажилтанд бүртгэлийн хэсгээс зөвхөн профайл байдаг тул шууд тийш нь
 * явуулна. Эхлээд өөр хуудсанд очоод дахин шилжвэл (`/account` -> `/account/orders` -> профайл) шилжилтүүд
 * мөргөлдөж, хуудас хоосон үлдэж болдог.
 */
export function landingPath(next: string, role: string | undefined) {
  const home = staffHome(role);
  if (home && SHOPPER_ACCOUNT.test(next)) return "/account/profile";
  return (next === "/" && home) || next;
}
