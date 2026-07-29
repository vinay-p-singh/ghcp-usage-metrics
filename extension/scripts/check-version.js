// Guard: package.json version must match the newest CHANGELOG.md entry.
// Runs in `vscode:prepublish` so `npm run package` / `vsce publish` fail fast
// when the version and changelog drift apart.
const fs = require("fs");
const path = require("path");

const extDir = path.resolve(__dirname, "..");
const pkg = JSON.parse(fs.readFileSync(path.join(extDir, "package.json"), "utf8"));
const changelog = fs.readFileSync(path.join(extDir, "CHANGELOG.md"), "utf8");

// First "## [x.y.z]" (or "## x.y.z") heading = the version being released.
const match = changelog.match(/^##\s*\[?(\d+\.\d+\.\d+)\]?/m);
if (!match) {
  console.error("check-version: no '## [x.y.z]' entry found in CHANGELOG.md.");
  process.exit(1);
}

const pkgVersion = pkg.version;
const changelogVersion = match[1];

if (pkgVersion !== changelogVersion) {
  console.error(
    `check-version: version mismatch.\n` +
      `  package.json : ${pkgVersion}\n` +
      `  CHANGELOG.md : ${changelogVersion} (newest entry)\n` +
      `Fix: bump package.json and add a matching '## [${pkgVersion}] — <date>' entry.`
  );
  process.exit(1);
}

// Warn (do not fail) if older .vsix files linger next to the new one.
const stale = fs
  .readdirSync(extDir)
  .filter((f) => f.endsWith(".vsix") && !f.includes(pkgVersion));
if (stale.length) {
  console.warn(`check-version: stale .vsix present (safe to delete): ${stale.join(", ")}`);
}

console.log(`check-version: OK (${pkgVersion} matches CHANGELOG.md).`);
