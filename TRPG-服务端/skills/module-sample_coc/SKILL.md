# SKILL · module-sample_coc（示例模组《图书馆搜证》带团技能）

> 给 KP/Agent：30 分钟短剧本（1920s 阿卡姆，1KP+3PL），文件 `modules/sample_coc/`，MIT 自研原创。

## 开团

1. 建桌开团：`POST /api/tables {table_id, campaign_id:c1, ruleset:coc7}` → 世界观朗读 `world_intro`（1925 年深秋，密信失窃，闭馆钟 30 分钟）。
2. 起始节点 `n1_front_desk`（前台：馆长+管理员），地图 `maps/library.json`（密大图书馆一层）。

## 节点路线（DAG，唯一回退边 n4→n3 带 once）

- n1 前台（问馆长/查登记簿）→ n2 阅览区（spot_hidden 找 `c1_torn_slip` 借书单残片）→ n3 古籍室现场（`c2_mud_print` 泥脚印）→ n4 锁芯困难 locksmith 检定 → n5 密室（`c3_candle` 蜡烛/`c5_ledger` 账本）→ n6 NPC 对话（三人，`c4_testimony`）→ n7 线索串联投票 → n8 对峙 → n9 真相（`e_good` 寻回密信 / `e_bad` 遗失）。
- condition 写法：`{check:{target,level}} | {clue:<id>} | {node:<id>}`，同层键 AND；consequences 只许 `clue_grant/npc_hook/map_reveal`。

## 带团要点

- 检定走 skill 名（spot_hidden/list/locksmith/psychology），难度 regular/hard/extreme；失败也有路（n5 通风管道备用线）。
- NPC：director（馆长·催结案有债务线）、clerk（管理员·目击关键）、borrower（神秘借阅人维克多·真凶嫌疑）。
- 结局条件：`e_good` = 抵达 n9_truth 且持有 `c6_letter`；否则 `e_bad`。
- 凶手 secret 只经 `secret_ref` 指针流转（KP 可见），当众复述前先查 `filter_state_jubensha` 口径。
