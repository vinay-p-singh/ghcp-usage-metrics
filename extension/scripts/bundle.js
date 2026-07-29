// Copies the Python extractor into the extension so a packaged .vsix is
// self-contained (findRepoRoot falls back to <extension>/py/usage.py).
const fs = require("fs");
const path = require("path");

const repo = path.resolve(__dirname, "..", ".."); // extension/scripts -> extension -> repo root
const dest = path.resolve(__dirname, "..", "py");
const files = ["usage.py", "dashboard_template.py"];
const packages = ["ghcp"]; // pure-helper package imported by usage.py

fs.mkdirSync(dest, { recursive: true });
for (const f of files) {
  const src = path.join(repo, f);
  if (!fs.existsSync(src)) {
    console.error(`bundle: missing ${src}`);
    process.exit(1);
  }
  fs.copyFileSync(src, path.join(dest, f));
  console.log(`bundle: ${f} -> py/${f}`);
}

for (const pkg of packages) {
  const srcDir = path.join(repo, pkg);
  if (!fs.existsSync(srcDir)) {
    console.error(`bundle: missing package ${srcDir}`);
    process.exit(1);
  }
  const destDir = path.join(dest, pkg);
  fs.mkdirSync(destDir, { recursive: true });
  for (const f of fs.readdirSync(srcDir)) {
    if (!f.endsWith(".py")) {
      continue;
    }
    fs.copyFileSync(path.join(srcDir, f), path.join(destDir, f));
    console.log(`bundle: ${pkg}/${f} -> py/${pkg}/${f}`);
  }
}

