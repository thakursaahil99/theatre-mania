import { NextResponse, type NextRequest } from "next/server";

/**
 * Route guard (UX only, the API enforces auth itself). `cv_session` is a non-secret marker
 * cookie the backend sets alongside the httpOnly tokens; if it is missing the user is
 * definitely signed out, so we send them to /login instead of rendering an empty page.
 */
const PROTECTED = ["/my-list", "/history", "/profiles", "/watch", "/admin"];

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (!PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return NextResponse.next();
  if (req.cookies.has("cv_session") || req.cookies.has("cv_access")) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/my-list/:path*", "/history/:path*", "/profiles/:path*", "/watch/:path*", "/admin/:path*"],
};
