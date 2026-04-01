# Paper-Feed: 自动化文献精准筛选与推送系统

[![GitHub Actions](https://img.shields.io/badge/Actions-Automated-blue.svg)](https://github.com/features/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### 系统概述
本工具是一个基于 GitHub Actions 的全自动文献监测系统。它旨在解决科研工作中的信息筛选效率问题，功能逻辑如下：
1.  **抓取**：定时从指定的期刊 RSS 源获取最新发表的论文。
2.  **筛选**：根据预设的关键词逻辑（支持 `AND` 组合）对标题和摘要进行匹配。
3.  **分发**：将命中的论文重组为标准化的 RSS 订阅源，供 Zotero 等阅读器订阅。

---

## 🛠 功能特性

*   **全自动运行**：无需服务器，利用 GitHub Actions 每 6 小时自动执行一次检索。
*   **多维度检索**：支持简单的关键词匹配及 `Keyword A AND Keyword B` 的组合逻辑检索。
*   **数据清洗**：内置 XML 字符清洗程序，自动移除非法字符，确保订阅源的兼容性与稳定性。
*   **隐私保护**：支持通过 GitHub Secrets 注入配置，隐藏用户的研究领域与关注列表。
*   **通用兼容**：生成的 `filtered_feed.xml` 遵循 RSS 2.0 标准，适配所有主流 RSS 阅读器。
*   **支持预印本补充**：可将 arXiv 主题查询 feed 与正式期刊 RSS 混合订阅，减少正式发表前的时间差。
*   **更适合 Zotero**：支持自定义 feed 标题、描述和重建模式，方便按研究方向维护订阅源。

---

## 🚀 部署流程

### 1. 初始化项目
1.  点击本页面右上角的 **Fork**，将仓库复制到你的账号下。
2.  在你的仓库中，删除根目录下的 `filtered_feed.xml` 文件（清除示例数据）。

### 2. 配置参数
提供两种配置方式，**涉及未发表 Idea 或敏感方向建议使用方式 B**。

#### 方式 A：文件配置（公开可见）
直接编辑仓库中的以下文件：
*   `journals.dat`：填入期刊 RSS 链接，一行一个。
*   `keywords.dat`：填入筛选关键词，一行一个。
    *   示例：`Perovskite AND Stability`

#### 方式 B：环境变量配置（私密不可见）
1.  进入仓库 **Settings** -> **Secrets and variables** -> **Actions**。
2.  点击 **New repository secret** 添加以下两个变量：
    *   **Name**: `RSS_JOURNALS` | **Secret**: 填入期刊链接（换行分隔）。
    *   **Name**: `RSS_KEYWORDS` | **Secret**: 填入关键词（换行分隔）。

可选增强变量：
*   `RSS_FEED_TITLE`：Zotero 中显示的订阅名称。
*   `RSS_FEED_DESCRIPTION`：订阅描述。
*   `RSS_FEED_LINK`：RSS channel 的链接地址；若不填，Actions 环境会自动按 GitHub Pages 地址推断。
*   `RSS_REBUILD_FROM_SCRATCH`：设为 `1` / `true` 时，运行时忽略旧的 `filtered_feed.xml`，适合切换研究方向后重建订阅。

### 3. 启动服务
1.  **配置 Pages**：
    *   进入 **Settings** -> **Pages**。
    *   **Build and deployment** 下，Source 选择 `GitHub Actions`。
    *   点击 **Save**。
2.  **激活 Workflow**：
    *   进入 **Actions** 页面。
    *   若提示 "Workflows aren't being run..."，点击绿色按钮 **I understand my workflows, go ahead and enable them**。
    *   选中左侧 **Auto RSS Fetch** -> **Run workflow** 手动触发首次运行。
    *   首次运行后，等待 `deploy` 任务完成，Pages 链接才会生效。

---

## 📈 客户端接入 (以 Zotero 为例)

1.  **获取订阅链接**：
    `https://{你的GitHub用户名}.github.io/{仓库名}/filtered_feed.xml`
2.  **添加订阅**：
    *   Zotero 菜单栏：`文件` -> `新建文献库` -> `新建订阅` -> `从网址`。
    *   粘贴上述链接。
3.  **设置同步频率**：
    *   建议在 Zotero 订阅设置中将更新时间设为 **6小时** 或更短，以匹配后端的更新频率。

---

## ⚠️ 维护说明

1.  **关键词优化**：若订阅源中无关论文过多，请检查 `keywords.dat` 是否过于宽泛；若漏掉重要论文，请检查是否拼写错误或逻辑过严。
2.  **活跃度维持**：GitHub 可能会暂停长期无代码提交仓库的 Actions 定时任务。若发现停止更新，请进入 Actions 页面手动启用或提交一次空的 Commit。(真的吗，AI说的我也不知道)
3.  **解析失败**：部分期刊 RSS 格式不规范。若遇到特定期刊抓取失败，请检查其 RSS XML 结构的合法性。
4.  **切换方向**：首次从泛领域订阅切到具体研究线时，建议启用 `RSS_REBUILD_FROM_SCRATCH=1`，避免旧 feed 历史条目继续残留在 Zotero 订阅中。
