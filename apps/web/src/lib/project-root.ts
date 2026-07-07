import { existsSync } from "fs";
import path from "path";

/** Resolve monorepo root from Next.js cwd (apps/web) or ATLAS_PROJECT_ROOT. */
export function findProjectRoot(startDir = process.cwd()): string {
  const envRoot = process.env.ATLAS_PROJECT_ROOT?.trim();
  if (envRoot && existsSync(path.join(envRoot, "scripts", "restart-api.ps1"))) {
    return path.resolve(envRoot);
  }

  let dir = startDir;
  for (let i = 0; i < 8; i++) {
    if (existsSync(path.join(dir, "scripts", "restart-api.ps1"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("Project Atlas root not found");
}
