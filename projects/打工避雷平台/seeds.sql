-- 示例数据（演示用，正式上线前可在面板里清空或替换）
INSERT OR IGNORE INTO video_allowlist (domain) VALUES
    ('bilibili.com'), ('douyin.com'), ('kuaishou.com'), ('channels.weixin.qq.com');

INSERT OR IGNORE INTO company (id, name, industry, city, scale, risk_level, tags, summary) VALUES
    (1, '示例科技有限公司', '互联网', '杭州', '100-499人', 2, '试用期不缴社保,强制大小周',
     '面试承诺与offer不一致，试用期不缴社保。'),
    (2, '示例人力资源服务部', '人力资源', '深圳', '20-99人', 3, '押金诈骗,虚假招聘',
     '以培训费、押金名义收费后失联。'),
    (3, '示例餐饮连锁', '餐饮', '成都', '500-999人', 1, '加班记录与实际不符',
     '排班表与工资条加班时长对不上。');

INSERT OR IGNORE INTO report (id, company_id, category, title, content, video_url, city, job,
                              status, ip_hash) VALUES
    (1, 1, '试用期社保', '试用期三个月不缴社保', '入职时口头承诺转正补缴，实际一直没缴。',
     '', '杭州', '前端开发', 'approved', 'seed'),
    (2, 2, '押金诈骗', '入职先交 2000 元培训费', '交完钱后对方微信拉黑，办公地点也空了。',
     'https://www.bilibili.com/video/示例占位', '深圳', '普工', 'approved', 'seed'),
    (3, 3, '加班', '排班表造假', '工资条显示的加班时长比实际少一半。',
     '', '成都', '服务员', 'pending', 'seed');
