# 贡献指南

感谢你关注并参与 OpenKidCar。这个项目希望让普通家庭也能借助 AI 亲手创造一辆智能儿童车，所以每一份贡献都很重要。

## 如何开始

1. Fork 本仓库到自己的账号。
2. Clone 到本地：

   ```bash
   git clone https://github.com/RevolutionLA/OpenKidCar.git
   ```

3. 创建功能分支：

   ```bash
   git checkout -b feat/your-change
   ```

4. 完成修改并提交，然后推送到你的 Fork。
5. 到 GitHub 发起 Pull Request，描述清楚改动内容和验证方式。

## 提交信息规范

建议使用简短、清晰的提交信息，格式为 `类型(范围): 描述`。

| 类型 | 用途 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修复问题 |
| `docs` | 文档改动 |
| `style` | 格式、排版调整 |
| `refactor` | 重构，不改变功能 |
| `test` | 测试 |
| `chore` | 构建、配置等杂项 |

示例：

```text
feat(firmware): add motor speed control
docs: update architecture overview
```

## 分支与发布

- `main` 是稳定分支，保持可发布状态。
- 新功能先在功能分支开发，通过 Pull Request 合入。
- 里程碑完成后打版本标签，例如 `v0.1.0`。

## 文档约定

- 架构与协议文档放在 `docs/`。
- 开发过程记录放在 `logs/开发日记/`，并在 `docs/development_log.md` 登记索引。
- 修改文档时尽量同步更新 README 中的相关说明。

## 开发环境

项目仍在搭建中，计划使用的环境如下：

- Arduino 固件：Arduino IDE 或 PlatformIO
- Raspberry Pi 软件：Python 3 + Raspberry Pi OS
- 电路设计：KiCad
- 三维建模：常见开源 CAD 工具

具体环境说明会在对应目录的文档中补充。

## Pull Request 检查清单

- 描述清楚改了什么、为什么改。
- 说明验证方式，例如编译通过、测试通过、实物验证。
- 涉及文档时同步更新相关文档。
- 保持改动范围聚焦，不要夹带无关修改。

## 许可证

提交内容即表示你同意以项目 [MIT License](LICENSE) 发布你的贡献。
