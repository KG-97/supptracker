#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('Usage: run-vite <command> [args...]');
  process.exit(1);
}

const command = args[0];
const viteArgs = args.slice(1);
const env = { ...process.env };

if (env.npm_config_http_proxy) {
  if (!env.npm_config_proxy) {
    env.npm_config_proxy = env.npm_config_http_proxy;
  }
  delete env.npm_config_http_proxy;
}

// On Windows, spawning a bare command does not consistently consult npm's
// .bin shim directory. Resolve the project-local Vite shim explicitly so the
// same npm scripts work in local shells and CI runners.
const localVite = join(
  process.cwd(),
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'vite.cmd' : 'vite',
);
const viteEntrypoint = join(process.cwd(), 'node_modules', 'vite', 'bin', 'vite.js');
const useNodeEntrypoint = process.platform === 'win32' && existsSync(viteEntrypoint);
const viteCommand = useNodeEntrypoint
  ? process.execPath
  : (existsSync(localVite) ? localVite : 'vite');
const viteCommandArgs = useNodeEntrypoint
  ? [viteEntrypoint, command, ...viteArgs]
  : [command, ...viteArgs];

const child = spawn(viteCommand, viteCommandArgs, {
  stdio: 'inherit',
  env,
  shell: false,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 0);
  }
});
