# Token 消耗优化规范（强制执行）

> **本项目规则**：所有 Claude 操作都必须遵守本规范节约 token。这是大项目，每步优化 1% 累计可观。

## 核心原则

1. **输出最小化** — 只看需要的部分，banner/装饰/空行一律过滤
2. **避免重复** — 同一文件不重复读，命令不重复跑
3. **批量代替串行** — 能一次查清楚的不要拆多次
4. **用 Edit 不用 Read+Edit** — 知道改什么就直接改，不读全文
5. **沉默成功，暴露失败** — 成功时少 echo，错误时多详情

---

## 一、SSH / 服务器操作

### 1. 屏蔽 1Panel banner（必做）

```bash
# 一次性（在远程服务器上）
ssh root@server "touch ~/.hushlogin"
```

之后 SSH 输出大幅减少。

### 2. 用 `tail -N` 限制输出

```bash
# ❌ 错：默认输出可能 100+ 行 banner
ssh ... "docker logs policy-radar-app"

# ✅ 对：只取最后 30 行
ssh ... "docker logs policy-radar-app --tail 30"
```

### 3. 用 grep 过滤无意义行

```bash
# ✅ 过滤 banner / 空行 / 装饰字符
ssh ... "docker logs app 2>&1" | grep -vE "^[█ ]+$|^\*+$|二维码|WeChat|qrcode"
```

### 4. 容器操作封装成单次

```bash
# ❌ 错：3 次 SSH（3 次 banner）
ssh ... "docker exec app cmd1"
ssh ... "docker exec app cmd2"
ssh ... "docker exec app cmd3"

# ✅ 对：1 次 SSH，3 条命令
ssh ... "docker exec app sh -c 'cmd1 && cmd2 && cmd3'"
```

### 5. 重启容器而非只 reload

```bash
# ❌ 错：restart 不重读 .env
ssh ... "docker compose restart app"

# ✅ 对：改 env 后必须 force-recreate
ssh ... "docker compose up -d --force-recreate app"
```

### 6. 容器崩溃循环时用 docker cp 而非 git pull

```bash
# 容器在 crash loop 时 git pull/rebuild 不起作用
# 直接 cp 新文件到容器 + 清 pyc
ssh ... "cat local.py | docker exec -i app sh -c 'cat > /app/path/file.py'"
ssh ... "docker exec app sh -c 'find /app -name __pycache__ -exec rm -rf {} +'"
ssh ... "docker restart app"
```

---

## 二、文件操作

### 1. Edit 不 Read+Edit

```bash
# ❌ 错：先 Read 全文（200 行）再 Edit
# ✅ 对：知道改什么就 Edit 一次
```

### 2. Grep 定位而非 Read 全文

```bash
# ❌ 错：Read 200 行文件找某行
# ✅ 对：grep -n 定位后 Edit
grep -n "specific_function" file.py
```

### 3. 写文件用 Write 不打印

```bash
# Write 整个文件比 echo 拼字符串更省 token
```

### 4. 改一处只显示 diff 不显示全文

```bash
git diff -- file.py | head -50
```

---

## 三、Bash 输出

### 1. tail 而不是 head（取末尾）

大多数时候最后一行最有信息。

### 2. -o /dev/null 吞掉不必要的主体输出

```bash
# 只看 http code
curl -s -o /dev/null -w "%{http_code}\n" http://...
```

### 3. 用 -w 格式化输出

```bash
# 多个测一次输出
for url in /health /api/sources; do
  echo -n "$url: "
  curl -s -o /dev/null -w "%{http_code}\n" "http://...$url"
done
```

### 4. 失败时多详情，成功时只 echo 关键

```bash
TOKEN=$(curl -s ... | python -c "..." 2>/dev/null)
[ -z "$TOKEN" ] && { echo "login failed"; exit 1; }
echo "ok"
```

### 5. 不要 cat 大文件

```bash
# ❌ 错
cat big.log

# ✅ 对
grep "ERROR" big.log | head -20
```

---

## 四、Python 内联脚本

### 1. 长 Python 用文件，不用 -c 多行

```bash
# ❌ 错：-c 多行难转义
ssh ... "python -c '
import sys
print(len(sys.argv))
...'"

# ✅ 对：stdin 喂
cat > /tmp/script.py << 'EOF'
...
EOF
ssh ... "cat /tmp/script.py | docker exec -i app sh -c 'cat > /tmp/s.py && python /tmp/s.py'"
```

### 2. 单行能用就用

```bash
# 单行就够
curl ... | python -c "import sys,json; print(json.load(sys.stdin)['key'])"
```

---

## 五、调试

### 1. 一次到位不反复试

```bash
# ❌ 错：跑 3 次看 3 个不同输出
# ✅ 对：先想清楚要什么，一次跑完
```

### 2. 用 tee 写文件 + 输出

```bash
# 既要输出又要落盘
cmd | tee /tmp/result.log
```

### 3. 错误信息截取关键 10 行

```bash
docker logs app --tail 100 2>&1 | grep -A 5 "Error" | head -20
```

---

## 六、Git 操作

### 1. 不用 status --porcelain=v

```bash
# 简洁
git status --short
```

### 2. log 用 --oneline

```bash
git log --oneline -10
```

### 3. 推送用 token URL（不交互）

```bash
git push https://USER:TOKEN@github.com/REPO.git main
```

---

## 七、HTTP 测试

### 1. 一次测多个端点

```bash
TOKEN=...
for ep in /health /api/sources /api/subscriptions; do
  echo -n "$ep: "
  curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" "http://...$ep"
done
```

### 2. 测连通用小 payload

```bash
curl -X POST ... -d '{}'  # 探活足够
```

### 3. 不要 cat 大 JSON

```bash
curl ... | python -c "import sys,json; d=json.load(sys.stdin); print(d['key'])"
```

---

## 八、对话策略

### 1. 少说废话

回复中避免：
- "我来帮你..."、"让我先看看..."
- "好的，我来..."
- "下面是..."

直接给结果 + 关键状态。

### 2. 总结在末尾，不在过程中

不要每步都说"现在做 X，下一步做 Y"，做完一次性总结。

### 3. 不显示完整 git diff（除非用户要看）

```bash
git diff --stat
```

### 4. 用户问"还有啥"才列

不要主动列全部已知信息。

### 5. 长 commit message 用 -m 分行

```bash
git commit -m "title" -m "body"  # body 单独一行
```

---

## 九、特定场景

### 1. 容器反复 Restart 死循环

- 不要等 30s 一次
- 看 `docker ps -a | grep app` 状态
- `docker logs --tail 5` 快速看
- 不行就 `docker rm` 重建

### 2. 看 OpenAPI 路由

```bash
curl -s host/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(sorted(d['paths'].keys())))"
```

### 3. 数据库快速探活

```bash
ssh ... "docker exec app python -c 'from python.models.base import init_session_factory, make_engine, get_session; from python.app.config import get_settings; e=make_engine(get_settings().database_url); init_session_factory(e); 
import asyncio
async def t():
    async with get_session() as s:
        from sqlalchemy import text
        r = await s.execute(text(\"select count(*) from subscriptions\"))
        print(r.scalar())
asyncio.run(t())'"
```

---

## 十、绝对禁止

- ❌ 读 200 行文件只为了找 1 行
- ❌ 跑命令不看输出就当成功
- ❌ 重复跑同一个命令（除非确认失败需要重试）
- ❌ 把整个 git diff 贴出来（用 --stat）
- ❌ 在 chat 里写 echo 调试
- ❌ 不限制 SSH 输出（banner 占大半 token）
- ❌ 用 Read 读已知内容的文件

---

## 检查清单（每条命令前过一遍）

- [ ] 这条命令的输出我能 `tail -N` 吗？
- [ ] 能不能跟其他命令合并到一次 SSH？
- [ ] 输出能不能 grep 过滤？
- [ ] 失败时输出够定位吗？
- [ ] 成功时输出够确认吗？

---

## 量化收益（一个 session 大致）

| 不优化 | 优化后 | 节省 |
|---|---|---|
| SSH banner ~1KB × 50 次 = 50KB | 屏蔽后 0 | -50KB |
| docker logs 全输出 ~5KB × 20 次 = 100KB | tail 30 + grep ~1KB × 20 = 20KB | -80KB |
| Read 全文 200 行 × 5 文件 = 30KB | grep 定位 + Edit × 5 = 5KB | -25KB |
| 每次 cat 大文件 ~3KB × 10 = 30KB | 跳过 / 替代 | -30KB |
| 重复命令 ~1KB × 10 = 10KB | 合并 / 不重复 | -10KB |

**单 session 节省：~200KB token（≈50K tokens）**

---

> 维护：Fangyi / 每次大改动后 review
