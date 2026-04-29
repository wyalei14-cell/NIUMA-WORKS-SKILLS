#!/usr/bin/env node
import process from "node:process";

const RPC_URL = process.env.NIUMA_RPC_URL || "https://testrpc.xlayer.tech/terigon";
const CORE = process.env.NIUMA_CORE || "0xcf52846E69a4772d5C9142d1487f4bb44d918cC5";

function arg(name, fallback = undefined) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

function fail(message, extra = {}) {
  console.error(JSON.stringify({ ok: false, error: message, ...extra }, null, 2));
  process.exit(1);
}

async function loadEthers() {
  try {
    return await import("ethers");
  } catch {
    fail("Missing dependency: install ethers v6 in this skill folder before using private-key-test signer.", {
      install: "npm install --prefix niuma-works-agent ethers@^6",
    });
  }
}

async function main() {
  const command = process.argv[2];
  if (!["address", "sign-message", "accept", "send"].includes(command)) {
    fail("Usage: node scripts/niuma_private_key_signer.mjs address | sign-message --message <text> | accept --task-id <id> --data <calldata>");
  }

  const privateKey = process.env.NIUMA_AGENT_PRIVATE_KEY;
  if (!privateKey || !/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
    fail("NIUMA_AGENT_PRIVATE_KEY is missing or invalid. Use only a funded test wallet and never commit it.");
  }

  const { ethers } = await loadEthers();
  if (command === "address") {
    const wallet = new ethers.Wallet(privateKey);
    console.log(JSON.stringify({ ok: true, address: wallet.address }, null, 2));
    return;
  }
  if (command === "sign-message") {
    const message = arg("--message");
    if (!message) fail("--message is required");
    const wallet = new ethers.Wallet(privateKey);
    const signature = await wallet.signMessage(message);
    console.log(JSON.stringify({ ok: true, address: wallet.address, signature }, null, 2));
    return;
  }

  const data = arg("--data");
  if (!data || !/^0x[0-9a-fA-F]+$/.test(data)) fail("--data hex calldata is required");
  const to = arg("--to", CORE);
  if (!/^0x[0-9a-fA-F]{40}$/.test(to)) fail("--to must be an EVM address");

  const expectedTaskId = arg("--task-id");
  const dryRun = process.argv.includes("--dry-run");
  const signOnly = process.argv.includes("--sign-only");
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const wallet = new ethers.Wallet(privateKey, provider);
  const network = await provider.getNetwork();
  const txRequest = {
    to,
    data,
    value: 0n,
    from: wallet.address,
  };

  const gasArg = arg("--gas-limit");
  let gasLimit;
  try {
    gasLimit = gasArg ? BigInt(gasArg) : await provider.estimateGas(txRequest);
  } catch (error) {
    if (!signOnly) throw error;
    gasLimit = gasArg ? BigInt(gasArg) : 200000n;
  }
  const fee = await provider.getFeeData();
  const tx = {
    to,
    data,
    value: 0n,
    gasLimit,
  };
  if (fee.maxFeePerGas && fee.maxPriorityFeePerGas) {
    tx.maxFeePerGas = fee.maxFeePerGas;
    tx.maxPriorityFeePerGas = fee.maxPriorityFeePerGas;
  } else if (fee.gasPrice) {
    tx.gasPrice = fee.gasPrice;
  }

  if (dryRun) {
    console.log(JSON.stringify({
      ok: true,
      dryRun: true,
      signer: wallet.address,
      chainId: network.chainId.toString(),
      to,
      taskId: expectedTaskId || null,
      gasLimit: gasLimit.toString(),
      data,
    }, null, 2));
    return;
  }

  if (signOnly) {
    const nonce = await provider.getTransactionCount(wallet.address, "pending");
    const populated = {
      ...tx,
      chainId: network.chainId,
      nonce,
      type: tx.maxFeePerGas ? 2 : 0,
    };
    const signedTx = await wallet.signTransaction(populated);
    console.log(JSON.stringify({
      ok: true,
      signOnly: true,
      signer: wallet.address,
      chainId: network.chainId.toString(),
      to,
      taskId: expectedTaskId || null,
      gasLimit: gasLimit.toString(),
      signedTx,
      broadcastWith: `onchainos gateway broadcast --signed-tx <signedTx> --address ${wallet.address} --chain xlayer`,
    }, null, 2));
    return;
  }

  const sent = await wallet.sendTransaction(tx);
  const receipt = await sent.wait();
  console.log(JSON.stringify({
    ok: true,
    signer: wallet.address,
    chainId: network.chainId.toString(),
    to,
    taskId: expectedTaskId || null,
    txHash: sent.hash,
    status: receipt?.status ?? null,
    blockNumber: receipt?.blockNumber ?? null,
    gasUsed: receipt?.gasUsed?.toString() ?? null,
  }, null, 2));
}

main().catch((error) => fail(error?.shortMessage || error?.message || String(error)));
