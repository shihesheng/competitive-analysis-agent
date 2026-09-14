-- 认证模块数据库初始化脚本（MySQL）
-- 用法：
--   mysql -u root -p < backend/sql/init_auth.sql
-- 或在 mysql 客户端内 source 本文件。
--
-- 默认账号：admin
-- 默认密码：123456 （下方 password_hash 为该密码的 bcrypt 哈希）
-- 注意：生产环境请务必修改默认密码。

CREATE DATABASE IF NOT EXISTS competitive_analysis
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE competitive_analysis;

CREATE TABLE IF NOT EXISTS users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(64) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'admin',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 插入默认管理员（已存在则忽略）。
-- password_hash 对应明文密码 123456 的 bcrypt 哈希。
INSERT IGNORE INTO users (username, password_hash, role)
VALUES (
  'admin',
  '$2b$12$02NnOmadtlX01qqI6NV7keTdKocv/fuOzlANPhtCx69R.Hm1lL146',
  'admin'
);
