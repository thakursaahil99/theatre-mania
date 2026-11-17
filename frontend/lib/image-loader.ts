// next/image custom loader: map requested widths onto TMDB's pre-rendered sizes.
// TMDB paths look like "/abc123.jpg"; absolute URLs (custom uploads) pass through.

const TMDB = "https://image.tmdb.org/t/p";
const WIDTHS = [92, 154, 185, 300, 342, 500, 780, 1280];

export default function imageLoader({ src, width }: { src: string; width: number; quality?: number }): string {
  if (/^https?:\/\//.test(src) || src.startsWith("data:")) return src;
  if (!src.startsWith("/")) return src;
  const size = WIDTHS.find((w) => w >= width);
  return `${TMDB}/${size ? `w${size}` : "original"}${src}`;
}
