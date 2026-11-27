import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import type { NextFetchEvent, NextRequest } from "next/server";

const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)"]);

const protectedMiddleware = clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export default async function proxy(request: NextRequest, event: NextFetchEvent) {
  const response = await protectedMiddleware(request, event);
  const rewrite = response?.headers.get("x-middleware-rewrite");
  if (response && rewrite) {
    const target = new URL(rewrite);
    // Clerk uses a same-page rewrite to forward auth request headers. On loopback,
    // Next can treat its normalized localhost URL as an external proxy back to
    // itself. Continue routing with those same request headers instead.
    if (target.hostname === "localhost" &&
        request.headers.get("host") === `127.0.0.1${target.port ? `:${target.port}` : ""}` &&
        target.pathname === request.nextUrl.pathname &&
        target.search === request.nextUrl.search) {
      response.headers.delete("x-middleware-rewrite");
      response.headers.set("x-middleware-next", "1");
    }
  }
  return response;
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
