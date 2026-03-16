import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

test("critical app routes exist", () => {
  const criticalFiles = [
    "app/page.tsx",
    "app/upload/page.tsx",
    "app/posts/[id]/page.tsx",
    "app/admin/page.tsx",
    "app/admin/imports/page.tsx",
    "app/admin/near-duplicates/page.tsx",
    "app/admin/rate-limits/page.tsx",
  ];
  for (const relativeFile of criticalFiles) {
    assert.equal(fs.existsSync(path.join(root, relativeFile)), true, `${relativeFile} is missing`);
  }
});

test("admin shell exposes key operations links", () => {
  const content = fs.readFileSync(path.join(root, "app/components/admin-shell.tsx"), "utf8");
  for (const needle of ["/admin/imports", "/admin/jobs", "/admin/rate-limits", "/admin/near-duplicates"]) {
    assert.match(content, new RegExp(needle.replaceAll("/", "\\/")));
  }
});
