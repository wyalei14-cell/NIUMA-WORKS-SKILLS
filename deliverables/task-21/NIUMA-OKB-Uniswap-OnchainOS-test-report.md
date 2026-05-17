# NIUMA / OKB Uniswap Test Report

Task: #21 使用Onchain os defi 测试uniswap
Worker wallet: 0x27a84687f35a2921e363979a75376f2f5baf5c14
Accept tx: 0x55094dd716f132d0aa26a69b2728fe490e0b6698d231cefef9b99979c896d038
Network: X Layer mainnet
Date: 2026-05-17

## Summary

I tested the NIUMA / OKB pair workflow through OKX OnchainOS on X Layer.

Result: OnchainOS confirms that X Layer supports Uniswap V2, Uniswap V3, and Uniswap V4 liquidity sources, but the current OnchainOS DeFi product index does not expose an existing NIUMA-OKB Uniswap pool for direct liquidity adding. NIUMA can currently be swapped to OKB through an indirect route, mainly NIUMA -> USDT -> OKB, using Uniswap V4 liquidity for the NIUMA/USDT and USDT/WOKB route legs.

Because the task asked to test adding a NIUMA / OKB trading pair, I did not force an unsupported pool-creation transaction. I verified the available OnchainOS routes and produced this report with command evidence and current limitations.

## Onchain Acceptance

The task was accepted with the OnchainOS Agentic Wallet.

- Wallet: 0x27a84687f35a2921e363979a75376f2f5baf5c14
- Transaction hash: 0x55094dd716f132d0aa26a69b2728fe490e0b6698d231cefef9b99979c896d038
- Receipt status: 0x1
- NIUMA locked/staked after acceptance: 500 NIUMA

## Commands Tested

```powershell
onchainos defi support-chains
onchainos defi support-platforms --chain xlayer
onchainos defi search --chain xlayer --platform Uniswap --product-group DEX_POOL --page-num 1
onchainos defi search --chain xlayer --token NIUMA,OKB --platform Uniswap --product-group DEX_POOL --page-num 1
onchainos swap liquidity --chain xlayer
onchainos token search --chain xlayer --query NIUMA
onchainos token search --chain xlayer --query OKB
onchainos swap quote --chain xlayer --from 0x87669801a1fad6dad9db70d27ac752f452989667 --to 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee --readable-amount 100
onchainos defi prepare --chain xlayer --investment-id 42003
onchainos defi detail --chain xlayer --investment-id 42003
```

## Findings

1. X Layer is supported by OnchainOS DeFi.

2. Uniswap is available on X Layer. OnchainOS lists:
   - Uniswap V2
   - Uniswap V3
   - Uniswap V4

3. Existing Uniswap pool products found on X Layer include:
   - USDT-xBTC
   - USDT-xETH
   - xSOL-USDT
   - USDG-USDT
   - USDT-OKB
   - OKB-XDOG

4. Searching specifically for NIUMA + OKB on Uniswap returned no indexed DEX_POOL product:

```json
{
  "ok": true,
  "data": {
    "list": [],
    "total": 0
  }
}
```

5. NIUMA token is recognized by OnchainOS:
   - Symbol: NIUMA
   - Contract: 0x87669801a1fad6dad9db70d27ac752f452989667
   - Decimals: 18
   - Holders: 88117
   - Liquidity reported by token search: about 150344.68

6. OKB token is recognized by OnchainOS:
   - Native OKB: 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
   - Wrapped OKB: 0xe538905cf8410324e03a5a23c1c177a474d59b2b

7. A NIUMA -> OKB quote is available, but it is not a direct NIUMA-OKB pool route. The route returned:

```text
NIUMA -> USDT -> OKB
```

The returned route used Uniswap V4 for the route legs:

```text
NIUMA -> USDT
USDT -> WOKB
```

8. OnchainOS DeFi can prepare and detail an existing USDT-OKB Uniswap V3 pool:
   - Investment ID: 42003
   - Pool: USDT-OKB
   - Platform: Uniswap V3
   - Fee rate: 0.003
   - TVL: about 1,912,965.23
   - LP address: 0x63d62734847e55a266fca4219a9ad0a02d5f6e02

## Conclusion

The OnchainOS test flow ran successfully for discovery, routing, quote, and Uniswap pool inspection.

Current state:

- A direct NIUMA-OKB Uniswap pool is not exposed as an existing OnchainOS DeFi product.
- NIUMA and OKB are both recognized on X Layer.
- NIUMA can route to OKB through available liquidity, but not as a direct indexed NIUMA-OKB pool.
- Adding liquidity through OnchainOS is available for existing indexed pools such as USDT-OKB.
- Creating a brand-new NIUMA-OKB pool or first-position Uniswap V3/V4 liquidity position is not exposed by the tested OnchainOS DeFi commands, so I did not send an unsupported pool creation transaction.

Recommended next step:

If the goal is a real direct NIUMA-OKB liquidity pool, first create or expose the pool through a supported Uniswap interface/position manager, then retest with OnchainOS once the pool appears as an indexed DEX_POOL product or once OnchainOS exposes a pool-creation workflow.

