# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.0.0] - 2025-11-16

### Added
- Initial release of Noob Bot
- Discord bot with multiple cogs (Economy, Fun, Misc, Nitro)
- Nitro promo command to distribute free Discord Nitro promotion codes
- Economy system with virtual currency (noob credits)
- Fun commands for entertainment
- Miscellaneous utility commands
- MongoDB integration for data persistence
- pCloud integration for file storage
- Web server health check endpoint
- Command cooldowns and user permissions
- Boost multipliers for nitro limits
- Automatic promo detection from Discord support page
- Embed status updates with bot statistics
- Owner-only administrative commands (toggle, sync, dm, msg)
- Guild-only command restrictions
- Channel and user blocking system

### Changed
- Blacklisted Wand promo (formerly known as WeMod)
- Added `promo` as an alias for the `nitro` command

### Features
- **Nitro Distribution**: Share Discord Nitro promo codes with configurable limits
- **Economy System**: Virtual currency system with balance tracking
- **Active Promo Detection**: Automatically checks for active Discord Nitro promotions
- **Boost Rewards**: Server boosters get increased daily limits
- **DM/Channel Options**: Send codes via DM or in channel
- **Usage Tracking**: Monitor daily nitro code usage per user
- **Admin Controls**: Toggle features, cogs, channels, and commands
- **Status Embeds**: Live bot statistics updates in configured channels
- **Custom Prefix**: Default command prefix `>`
