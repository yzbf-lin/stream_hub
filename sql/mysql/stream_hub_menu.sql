UPDATE sys_menu
SET
  title = 'stream_hub.log_console_menu',
  path = '/monitor/log-console',
  sort = 6,
  icon = 'lucide:file-search',
  type = 1,
  component = '/plugins/stream_hub/views/log-viewer',
  perms = NULL,
  status = 1,
  display = 1,
  cache = 1,
  link = '',
  remark = '实时日志',
  parent_id = (SELECT id FROM (SELECT id FROM sys_menu WHERE name = 'Monitor' LIMIT 1) AS tmp_monitor_root),
  updated_time = CURRENT_TIMESTAMP
WHERE name = 'PluginStreamHubLogConsole';

INSERT INTO sys_menu (title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, created_time, updated_time)
SELECT
  'stream_hub.log_console_menu',
  'PluginStreamHubLogConsole',
  '/monitor/log-console',
  6,
  'lucide:file-search',
  1,
  '/plugins/stream_hub/views/log-viewer',
  NULL,
  1,
  1,
  1,
  '',
  '实时日志',
  (SELECT id FROM (SELECT id FROM sys_menu WHERE name = 'Monitor' LIMIT 1) AS tmp_monitor_root),
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE name = 'PluginStreamHubLogConsole'
);

UPDATE sys_menu
SET
  title = '查看',
  path = NULL,
  sort = 0,
  icon = NULL,
  type = 2,
  component = NULL,
  perms = 'stream_hub:log:view',
  status = 1,
  display = 0,
  cache = 1,
  link = '',
  remark = NULL,
  parent_id = (SELECT id FROM (SELECT id FROM sys_menu WHERE name = 'PluginStreamHubLogConsole' LIMIT 1) AS tmp_parent),
  updated_time = CURRENT_TIMESTAMP
WHERE name = 'ViewStreamHubLog';

INSERT INTO sys_menu (title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, created_time, updated_time)
SELECT
  '查看',
  'ViewStreamHubLog',
  NULL,
  0,
  NULL,
  2,
  NULL,
  'stream_hub:log:view',
  1,
  0,
  1,
  '',
  NULL,
  (SELECT id FROM (SELECT id FROM sys_menu WHERE name = 'PluginStreamHubLogConsole' LIMIT 1) AS tmp_parent),
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE name = 'ViewStreamHubLog'
);
