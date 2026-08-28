import Link from "next/link";

/**
 * The default Next.js 404 says "This page could not be found." on a bare white
 * page with no way out. Somebody who followed a link to a product they deleted
 * lands here, and a dead end is where a non-technical user stops and asks a
 * colleague what they broke.
 */
export default function NotFound() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-16 sm:px-6" data-testid="not-found">
      <h1 className="t-large-title">This page is not here</h1>
      <p className="t-body t-secondary prose-measure mt-3">
        Either the address is wrong, or whatever was here has been deleted since the link was made.
        Nothing has gone wrong with your data.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/" className="btn btn-primary" data-testid="not-found-home">
          Go to your products
        </Link>
        <Link href="/rules" className="btn btn-secondary">
          See the rules you have added
        </Link>
      </div>
    </main>
  );
}
