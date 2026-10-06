# Pantryfifo · 冰箱临期先吃

分批入库 → FEFO 扣减 → 过期下架。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5300 |
| API | 10300 |

0-1：`shopping_list` / `recipe_suggest` / `temp_zone`。

## 手钉可放天数（override_days）

在架批可 `POST /api/lots/{id}/override` 写入钉值（正整数，非正数 400 拒写；`null` 清除）：

- 生效到期日 = 写入日 + `override_days`；顶条紧急吃写入值，全层主行仍显示入库到期日。
- 顶条 / 批次详情 / 过期下架 / FEFO 共用同一条生效到期日规则（`app/modules/override_days`），
  日历已过期批钉后三者同一资格；`warn_days` 每次求值现读，改基后各视图一致。
- 批次详情页（点批次进入）提交天数后，顶条与详情对同一批得出同一紧急结论。
