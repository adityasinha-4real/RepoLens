import Link from "next/link";
import { LensIcon } from "./ui/icons";

export function SiteHeader({ children }: { children?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-20 print:hidden border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-7xl items-center gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-6 place-items-center rounded bg-foreground text-background">
            <LensIcon size={14} />
          </span>
          RepoLens
        </Link>
        <div className="min-w-0 flex-1">{children}</div>
        <span className="hidden text-xs text-muted sm:inline">
          Static analysis · repository code is never executed
        </span>
      </div>
    </header>
  );
}
