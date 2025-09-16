#!/usr/bin/env node
import { spawn } from 'node:child_process';

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

const child = spawn('vite', [command, ...viteArgs], {
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
