import Link from "next/link";

export default function NotFound() {
  return (
    <div className="relative grid min-h-[80svh] place-items-center overflow-hidden px-4 text-center">
      <div className="absolute left-1/2 top-1/3 size-[40rem] -translate-x-1/2 rounded-full bg-accent/15 blur-[140px]" />
      <div className="relative">
        <p className="font-display text-[clamp(6rem,22vw,16rem)] leading-none text-gradient">404</p>
        <h1 className="mt-2 text-2xl font-semibold">This reel is missing.</h1>
        <p className="mt-3 text-white/55">The page you&apos;re looking for was cut in the edit.</p>
        <Link href="/" className="btn-primary mt-8">Back to home</Link>
      </div>
    </div>
  );
}
