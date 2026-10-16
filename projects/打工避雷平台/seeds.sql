-- 示例数据（演示用，正式上线前替换）
-- 视频链接只接受四大平台：B站 / 抖音 / 快手 / 视频号
INSERT OR IGNORE INTO video_allowlist (domain) VALUES
    ('bilibili.com'), ('douyin.com'), ('kuaishou.com'), ('channels.weixin.qq.com');

INSERT OR IGNORE INTO company
    (id, name, credit_code, industry, city, province, scale, risk_level, tags, summary,
     appeal_status, appeal_count, appeal_note) VALUES
    (1, '示例科技有限公司', '91330106MA2CD1E47X', '互联网', '杭州', '浙江', '100-499人', 2,
     '试用期不缴社保,强制大小周', '面试承诺与 offer 不一致，试用期不缴社保。',
     'none', 0, ''),
    (2, '示例人力资源服务部', '91440300MA5EX8KQ2P', '人力资源', '深圳', '广东', '20-99人', 3,
     '押金诈骗,虚假招聘', '以培训费、押金名义收费后失联。',
     'pending', 1, '称收费由第三方培训机构收取，正在核验凭证。'),
    (3, '示例餐饮连锁', '', '餐饮', '成都', '四川', '500-999人', 1,
     '加班记录与实际不符', '排班表与工资条加班时长对不上。',
     'none', 0, ''),
    (4, '示例物流有限公司', '91410100MA3X2F9L7B', '物流运输', '郑州', '河南', '1000人以上', 3,
     '拖欠工资,离职克扣', '连续两个月延迟发薪，离职时克扣最后一个月工资。',
     'rejected', 1, '称考勤数据缺失导致延迟，未提供有效凭证，申诉驳回。'),
    (5, '示例电子商务有限公司', '91310115MA1K2B8X7C', '电子商务', '上海', '上海', '100-499人', 3,
     '拖欠工资,虚假招聘', '以"合伙人"名义规避社保，工资随绩效浮动。',
     'accepted', 1, '已采纳部分更正：补充说明为合作关系，正文保留原描述。');

-- 上传免审直发：status 一律 approved，不再有 pending 记录
INSERT OR IGNORE INTO report (id, company_id, category, title, content, video_url, city, job,
                              status, ip_hash) VALUES
    (1, 1, '试用期社保', '试用期三个月不缴社保', '入职时口头承诺转正补缴，实际一直没缴。',
     '', '杭州', '前端开发', 'approved', 'seed'),
    (2, 2, '押金诈骗', '入职先交 2000 元培训费', '交完钱后对方微信拉黑，办公地点也空了。',
     'https://www.bilibili.com/video/示例占位', '深圳', '普工', 'approved', 'seed'),
    (3, 3, '加班', '排班表造假', '工资条显示的加班时长比实际少一半。',
     '', '成都', '服务员', 'approved', 'seed'),
    (4, 4, '拖欠工资', '连续两个月延迟发放', '工资从每月 10 号拖到 25 号以后才发。',
     '', '郑州', '分拣员', 'approved', 'seed'),
    (5, 5, '试用期社保', '签合作协议不缴社保', '入职让签"合作框架协议"，不缴社保。',
     '', '上海', '电商运营', 'approved', 'seed');

-- 申诉记录（只有申诉走平台审核）
INSERT OR IGNORE INTO appeal
    (id, company_id, company_name, credit_code, reason, evidence, status, review_note, created_at) VALUES
    (1, 2, '示例人力资源服务部', '91440300MA5EX8KQ2P',
     '收费由第三方培训机构收取，与本公司无关，附合作协议与收款方信息。',
     '合作协议, 收款方凭证', 'pending', '', '2026-05-12 10:20:00'),
    (2, 4, '示例物流有限公司', '91410100MA3X2F9L7B',
     '延迟发放系考勤数据缺失所致，非恶意拖欠，申请更正描述。',
     '考勤系统导出记录', 'rejected', '未提供有效凭证，申诉驳回。', '2026-06-22 15:40:00'),
    (3, 5, '示例电子商务有限公司', '91310115MA1K2B8X7C',
     '双方为合作关系而非劳动关系，申请补充说明。',
     '合作协议', 'accepted', '已补充合作关系的说明，原记录保留。', '2026-09-12 09:05:00');
