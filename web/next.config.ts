import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Pin the workspace root: without this Turbopack walks up past the repo and
  // picks up an unrelated lockfile in the home directory.
  turbopack: { root: __dirname },
};

export default config;
