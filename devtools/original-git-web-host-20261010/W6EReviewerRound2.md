# W6.E 獨立工程 reviewer 兩輪紀錄

2026-10-11。Reviewer `/root/w6_independent_review` 依使用者明確要求進行唯讀複查，與主 agent 分開讀原始檔案、重算 hash、真 VerifiedOwnerBundle.load、執行限定 source 負例。没有執行正式 main、原生 renderer、private state或外部服務。

## 第一輪：使用者原生證據

Reviewer 獨立確認兩輪 74 unique checks／70 required／13 source SHA、分離與內嵌 SecurityEvidence、FormalPreflight、真 signed bundle load／CSP／immutable map 與既有 owner接線均一致；限定範圍無 P1/P2。

限制：receipt JSON 本身未簽章；asset builder自簽不等於publisher信任。VBS既有接線不需要修改，flip pin後正式 cold start會讀私態與啟動既有 lifecycle；套件requirements仍非完整distribution宣告。歷史合併popup FAIL不回填唯一原因。

## 第二輪：新增 verifier／validation／退役圖

| Finding | 修正與證據 |
| --- | --- |
| P2：只核項目數，source／package／module／DLL可以換名稱；origin只看env containment也可冒用另一個DLL。 | 精確13 source集合取自harness AST；固定3 packages／7 modules／6 DLL names，逐項精確origin／prefix／Qt lib path。獨立mutation重驗全部拒絕。 |
| P2：navigation只信pass=true，未驗raw callback與hit計數。 | 要求deniedCallbacks=3及probeHitsBefore=After=1；偽造pass加hit／零拒絕負例均拒絕。 |
| 使用者指出 child不存在OwnerBuild.json。 | 實際directory確認；核NativeResult.bundle＋canonical owner-build＋真staging OwnerBuild，不創建missing receipt。 |
| 使用者指出錯呼 evaluator.evaluate。 | 改canonical evaluate_security；記憶體舊版AttributeError fail-before與同一測試pass-after，见EvaluatorRegression.json。 |
| 主agent末驗：Windows換行使patch不能套用。 | 改LF byte輸出；candidate-reviewed完整dry-run及git apply --check PASS，早期patch明列不可用。正式pin未套用。 |

Reviewer 已獨立以8個記憶體mutation probes重驗兩P2，全部REJECTED；再次核raw pair的13+13 source。source-only ReleaseReviewTests通過；constructor測試已讀碼確認使用真existing-window constructor，但替換WebEngine surface，不能當native驗收。

Widgets圖只為條件式規劃，含shared/lifecycle/modal與core-pages defer，無刪除operation。新文件保留W6.E automation PASS／W6.F MANUAL_PENDING／W7 TECHNICAL_READINESS_SCOPED。最終revision與保全複核另記本輪 evidence `ReviewerFinal.json`。

這是獨立工程複核，不等於外部publisher審核、使用者視覺批准或正式產品release。所有human gate仍待使用者完成。
