# Account Proxy Persistence & Routing Priority

> **日期**: 2026-09-26  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Исправление бага с незаписывающейся прокси аккаунта и обеспечение приоритета индивидуальной прокси над глобальной

**内容**: Исправлено сохранение и приоритет индивидуальной прокси аккаунта:
1. В `account_store.py` добавлена функция `update_account_proxy(account_id, proxy)`, обновляющая колонку `proxy` в таблице `accounts` (SQLite).
2. В `pool_manager.py:set_account_proxy` обновляется как SQLite хранилище, так и файл манифеста. До этого метод искал аккаунт только в манифесте и не обновлял БД, из-за чего в `list_accounts()` при релоаде всегда отображался прочерк.
3. В `oauth_refresh.py` (запрос квот `retrieve_account_quota` и рефреш токенов `ensure_fresh_sqlite_account`) все запросы теперь строго используют индивидуальную прокси аккаунта `effective_proxy = get_google_proxy(proxy or sqlite_account.get('proxy'))`.
4. В `agy_http_client.py:stream_completion` и `generate_image` прокси аккаунта (`pool_proxy`) имеет безусловный приоритет над глобальной.
5. Для добавленного аккаунта `mod989424-58e018` прописана прокси `http://vasa88885_gmail_com:486f205d78@83.171.235.118:30017`, профиль Daniel Moon успешно сохранен.
