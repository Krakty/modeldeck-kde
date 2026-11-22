import Foundation
import Testing
@testable import ModelDeckMacCore

/// Issue #868 (Tim, 2026-11-21): the Mac lists every card the usage page has.
/// A page card no account on this Mac matches comes through read-only, and a
/// Fable weekly read from Claude Code's undocumented field says "unconfirmed".
@Suite("Issue #868 — every usage-page card, read-only")
struct Issue868PageCardsTests {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private let iso = ISO8601DateFormatter()

    private func stateJSON(withPageCards: Bool) -> Data {
        let observed = iso.string(from: now.addingTimeInterval(-120))
        let cards = withPageCards ? #","pageCards":[{"id":"page:0123456789ab","provider":"claude","label":"Team Seat","team":true,"usage":["#
            + #"{"accountId":"page:0123456789ab","scope":"weekly","usedPercent":21,"remainingPercent":79,"observedAt":"\#(observed)","source":"pool-hub","stale":false,"detail":{},"hubSource":"Studio · T3"},"#
            + #"{"accountId":"page:0123456789ab","scope":"Fable weekly","usedPercent":30,"remainingPercent":70,"observedAt":"\#(observed)","source":"pool-hub","stale":false,"detail":{"unconfirmed":true},"hubSource":"Studio · T3"}]}]"#
            : ""
        return Data((#"{"accounts":[{"id":"deck","provider":"claude","label":"ModelDeck","enabled":true,"isDefault":false}],"usage":[]"# + cards + "}").utf8)
    }

    @Test func TRIPWIRE_pageCardIsListedReadOnlyUnderItsProvider() throws {
        let state = try JSONDecoder().decode(DeckState.self, from: stateJSON(withPageCards: true))
        let claude = try #require(DeckBuilder.columns(state: state, sortOrder: .lowestRemaining, now: now).first { $0.provider == .claude })
        let card = try #require(claude.pageCards.first)
        #expect(claude.pageCards.count == 1)
        #expect(card.label == "Team Seat" && card.team)
        #expect(card.windows.map(\.remainingPercent) == [79, 70])
        #expect(card.windows[1].title.hasSuffix(" (unconfirmed)"))
        #expect(!card.windows[0].title.contains("unconfirmed"))
        #expect(card.sourceText == "Read 2 min ago · Studio · T3 · from the usage page")
        #expect(claude.subscriptionCountText == "1 subscription", "a page card is not one of this Mac's subscriptions")
        #expect(!claude.rows.contains { $0.id == card.id })
    }

    /// Tim, 2026-11-22: a page card showing every line at once looked forced.
    /// It leads with one line, picked by the same rule as an account card.
    @Test func TRIPWIRE_pageCardLeadsWithOneLineLikeAnAccountCard() throws {
        let state = try JSONDecoder().decode(DeckState.self, from: stateJSON(withPageCards: true))
        func lead(_ setting: DeckLeadWindow) throws -> DeckWindow? {
            let claude = try #require(DeckBuilder.columns(state: state, sortOrder: .lowestRemaining, now: now, leadWindow: setting).first { $0.provider == .claude })
            let card = try #require(claude.pageCards.first)
            #expect(card.provider == .claude, "the card carries its provider so the deck can show its mark")
            #expect(card.lead == DeckAccountRow.leadWindow(in: card.windows, provider: .claude, leadWindow: setting, prefersGeneralWeeklyHeadline: false))
            return card.lead
        }
        #expect(try lead(.lowest)?.remainingPercent == 70)
        #expect(try lead(.generalWeekly)?.remainingPercent == 79)
    }

    /// #869 review: a Mac whose only cards come from the page shows them,
    /// not the empty-deck add-account screen, in either layout.
    @Test func aDeckWithOnlyPageCardsIsNotEmpty() throws {
        var state = try JSONDecoder().decode(DeckState.self, from: stateJSON(withPageCards: true))
        state.accounts = []
        for layout in [DeckLayout.twoColumn, .singleColumn] {
            #expect(!DeckPopoverModel.isDeckEmpty(state: state, layout: layout, now: now))
        }
        state.pageCards = []
        #expect(DeckPopoverModel.isDeckEmpty(state: state, layout: .singleColumn, now: now))
    }

    /// #869 review: VoiceOver can open a page card to its other lines. A
    /// source check, since this package has no SwiftUI view harness; it
    /// fails if the card's tap loses its accessibility twin.
    @Test func TRIPWIRE_pageCardExpandsFromVoiceOver() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let source = try String(contentsOf: root.appendingPathComponent("Sources/ModelDeckMac/DeckPopoverView.swift"), encoding: .utf8)
        let start = try #require(source.range(of: "struct DeckPageCardRowView: View {"))
        let end = try #require(source.range(of: "// MARK: - Type scale", range: start.upperBound..<source.endIndex))
        let card = source[start.upperBound..<end.lowerBound]
        #expect(card.contains(".onTapGesture { isExpanded.toggle() }"))
        #expect(card.contains(".accessibilityAction { isExpanded.toggle() }"))
        #expect(card.contains(".accessibilityElement(children: .combine)"), "one element, not a button per text")
    }

    @Test func olderDaemonWithoutPageCardsDecodesToNone() throws {
        let state = try JSONDecoder().decode(DeckState.self, from: stateJSON(withPageCards: false))
        #expect(state.pageCards.isEmpty)
        #expect(DeckBuilder.columns(state: state, sortOrder: .lowestRemaining, now: now).allSatisfy { $0.pageCards.isEmpty })
    }
}
