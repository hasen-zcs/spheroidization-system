-- 建表语句。
--
-- 这份是从建库的人那里原样抄过来的，一个字都没改。
-- 他再发新的 DDL 时，整份替换这个文件就行，不要在 Python 字符串里手抄，
-- 上次他把两个外键从 INT 改成 INTEGER，手抄很容易漏。
--
-- 执行入口在 connection.py 的 create_tables()。

CREATE TABLE StandardRecord (
	standard_record_id INTEGER PRIMARY KEY AUTOINCREMENT,--主键，id自增
	standard_spheroidization_time REAL NOT NULL DEFAULT 70 CHECK (standard_spheroidization_time BETWEEN 65 AND 75),-- 球化时长（秒），默认70，限制在65到75之间
	standard_entry_length REAL NOT NULL CHECK (standard_entry_length > 0),-- 入料长度
	weighing_standard REAL NOT NULL,--称重标准
	created_at TEXT NOT NULL,-- 创建检测标准时间
	created_by TEXT NOT NULL,-- 创建人
	remark TEXT-- 备注
) STRICT;

CREATE TABLE SpheroidizationRecord (
	spheroidization_record_id INTEGER PRIMARY KEY AUTOINCREMENT,--主键，id自增
	standard_record_id INTEGER NOT NULL, --溯源：引用使用哪一套标准，仅做溯源，业务运算使用快照值
	detection_time TEXT NOT NULL,-- 检测时间
	spheroidization_start_time TEXT NOT NULL,-- 球化开始时间
	spheroidization_end_time TEXT NOT NULL,-- 球化结束时间
	actual_spheroidization_time REAL, -- 实际反应时间（秒)
	standard_spheroidization_time REAL NOT NULL,-- 快照：生成记录那一刻的标准球化时间，算法、报表使用此字段
	spheroidization_abnormal INTEGER CHECK (spheroidization_abnormal IN (0, 1)),-- 机器判定球化反应是否异常，0正常,1异常
	processed INTEGER NOT NULL DEFAULT 0 CHECK (processed IN (0, 1)),-- 人工是否处理(默认为0未处理，已处理为1）
	processed_at TEXT,-- 人工处理时间
	processed_by TEXT,-- 处理人
	CHECK((processed = 1 AND processed_at IS NOT NULL AND processed_by IS NOT NULL)OR(processed = 0 AND processed_at IS NULL AND processed_by IS NULL)),--一条球化记录只允许一次人工处置，处置完成不可逆，不会回退状态。防止出现“状态标记为已处理，但实际上没有处理人、也没有处理时间”或者“状态为未处理，但实际有处理人或时间”的“幽灵数据”
	FOREIGN KEY (standard_record_id) REFERENCES StandardRecord(standard_record_id) ON DELETE RESTRICT--外键仅仅是记录来源标识，不是用来实时取参数！ON DELETE RESTRICT，一旦有球化记录引用该标准，禁止删除标准，防止溯源ID变成孤儿id。
) STRICT;

CREATE TABLE ReviewRecord (
    review_record_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 主键，id自增
    spheroidization_record_id INTEGER NOT NULL, -- 关联的球化记录ID
    review_result INTEGER NOT NULL CHECK (review_result IN (0, 1)), -- 人工复核结果， 0正常, 1异常
    review_remark TEXT, -- 复核备注，可为空
    reviewer TEXT NOT NULL, -- 复核人
    reviewed_at TEXT NOT NULL, -- 复核时间
    -- 外键约束
    FOREIGN KEY (spheroidization_record_id) REFERENCES SpheroidizationRecord(spheroidization_record_id) ON DELETE RESTRICT
) STRICT;
