-- 建表语句。
-- 发新的 DDL 时，整份替换这个文件就行
-- 执行入口在 connection.py 的 create_tables()。

CREATE TABLE StandardRecord (
	standard_record_id INTEGER PRIMARY KEY AUTOINCREMENT,--主键，id自增
	standard_spheroidization_time REAL NOT NULL CHECK(standard_spheroidization_time > 0),-- 球化时长
	standard_spheroidization_time_upper REAL,--球化时长上限
	standard_spheroidization_time_lower REAL,--球化时长下限
	weighing_standard REAL NOT NULL,--称重标准
	created_at TEXT NOT NULL,-- 创建检测标准时间
	created_by TEXT NOT NULL,-- 创建人
	remark TEXT-- 备注
) STRICT;

CREATE TABLE SpheroidizationRecord (
	spheroidization_record_id INTEGER PRIMARY KEY AUTOINCREMENT,--主键，id自增
	standard_record_id INTEGER NOT NULL, --溯源：引用使用哪一套标准，仅做溯源，业务运算使用快照值
	detection_time TEXT NOT NULL,-- 检测时间
	spheroidization_start_time TEXT,
	spheroidization_end_time TEXT,
	actual_spheroidization_time REAL, 
	standard_spheroidization_time REAL NOT NULL,-- 快照：生成记录那一刻的标准球化时间，算法、报表使用此字段
	spheroidization_abnormal INTEGER CHECK (spheroidization_abnormal IN (0, 1)),-- 机器判定球化反应是否异常，0正常,1异常
	abnormal_type INTEGER CHECK (abnormal_type IN (1, 2, 3, 4, 5, 6)),-- 异常分类，1进站未球化,2球化线滑动/进线提前中止,3超过标准,4低于标准
	abnormal_reason TEXT,-- 异常的文字说明，由上游检测设备给出，原样入库不做二次判断
	processed INTEGER NOT NULL DEFAULT 0 CHECK (processed IN (0, 1)),-- 人工是否处理(默认为0未处理，已处理为1）
	processed_at TEXT,-- 人工处理时间
	processed_by TEXT,-- 处理人
	spheroidization_wire_entry_start_time TEXT NOT NULL,-- 进线开始时间
	spheroidization_wire_entry_end_time TEXT NOT NULL,-- 进线结束时间
	spheroidization_wire_entry_total_duration REAL NOT NULL,-- 进线总时长
	spheroidization_weight REAL NOT NULL,-- 重量
	spheroidization_image BLOB,-- 图片二进制数据
	CHECK((processed = 1 AND processed_at IS NOT NULL AND processed_by IS NOT NULL)OR(processed = 0 AND processed_at IS NULL AND processed_by IS NULL)),
	--一条球化记录只允许一次人工处置，处置完成不可逆，不会回退状态。防止出现“状态标记为已处理，但实际上没有处理人、也没有处理时间”或者“状态为未处理，但实际有处理人或时间”的“幽灵数据”
	FOREIGN KEY (standard_record_id) REFERENCES StandardRecord(standard_record_id) ON DELETE RESTRICT
	--外键仅仅是记录来源标识，不是用来实时取参数！ON DELETE RESTRICT，一旦有球化记录引用该标准，禁止删除标准，防止溯源ID变成孤儿id。
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

CREATE TABLE TemperatureRecord (
	temperature_record_id INTEGER PRIMARY KEY AUTOINCREMENT, 
	gun_no INTEGER NOT NULL, -- 测温枪号，现场多把枪各报各的
	temperature REAL NOT NULL,
	measured_at TEXT NOT NULL,
	spheroidization_record_id INTEGER, -- 可空：温度可能先到、对应的球化记录还没生成
	created_at TEXT NOT NULL, -- 入库时间
	-- 球化记录被删时置空而不是级联删除：温度是独立测出来的事实，
	-- 不能因为球化记录没了就整条丢掉，否则测温枪的数据就断档了。
	FOREIGN KEY (spheroidization_record_id) REFERENCES SpheroidizationRecord(spheroidization_record_id) ON DELETE SET NULL
) STRICT;

CREATE TABLE StandardSwitchLogs (
	switch_log_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 主键，id自增
	switched_at TEXT NOT NULL, -- 切换时刻
	from_standard_record_id INTEGER, -- 可空：库里还没有任何标准时第一次切换，没有“原标准”
	to_standard_record_id INTEGER NOT NULL, -- 切到哪一套
	operated_by TEXT NOT NULL, -- 操作人，取登录账号
	reason TEXT NOT NULL CHECK(length(trim(reason)) > 0), -- 切换原因，前后不能全是空格
	-- RESTRICT 双向：被切换记录引用过的标准不许删，否则日志里的“从哪套切到哪套”就断链了。
	FOREIGN KEY (from_standard_record_id) REFERENCES StandardRecord(standard_record_id) ON DELETE RESTRICT,
	FOREIGN KEY (to_standard_record_id) REFERENCES StandardRecord(standard_record_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE UserAccount (
	user_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 主键，id自增
	username TEXT NOT NULL UNIQUE, -- 登录名，重复建号直接报错
	password_hash TEXT NOT NULL, -- 只存哈希，不存明文
	enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)), -- 是否启用，0停用1启用
	is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)), -- 1=全权限。留一个不可能被权限表锁死的入口
	created_by TEXT NOT NULL, -- 建号人
	created_at TEXT NOT NULL -- 建号时间
) STRICT;

CREATE TABLE UserPermission (
	user_id INTEGER NOT NULL, -- 外键 → UserAccount
	permission_key TEXT NOT NULL, -- 页面/功能标识，例如 page:records、action:review
	PRIMARY KEY (user_id, permission_key), -- 联合主键：同一个用户同一个权限只存一条
	-- CASCADE：删用户时他的权限跟着清掉，不留孤儿权限行。
	FOREIGN KEY (user_id) REFERENCES UserAccount(user_id) ON DELETE CASCADE
) STRICT;

-- 删除后把 AUTOINCREMENT 序列回退到当前最大 ID。
-- 删除中间行时序列不变；删除最后一行时下一条会复用被删除的 ID。
CREATE TRIGGER IF NOT EXISTS standard_sync_sequence
AFTER DELETE ON StandardRecord
BEGIN
    UPDATE sqlite_sequence
       SET seq = (
           SELECT COALESCE(MAX(standard_record_id), 0)
           FROM StandardRecord
       )
     WHERE name = 'StandardRecord';
END;

CREATE TRIGGER IF NOT EXISTS spheroidization_sync_sequence
AFTER DELETE ON SpheroidizationRecord
BEGIN
    UPDATE sqlite_sequence
       SET seq = (
           SELECT COALESCE(MAX(spheroidization_record_id), 0)
           FROM SpheroidizationRecord
       )
     WHERE name = 'SpheroidizationRecord';
END;

CREATE TRIGGER IF NOT EXISTS review_sync_sequence
AFTER DELETE ON ReviewRecord
BEGIN
    UPDATE sqlite_sequence
       SET seq = (
           SELECT COALESCE(MAX(review_record_id), 0)
           FROM ReviewRecord
       )
     WHERE name = 'ReviewRecord';
END;
