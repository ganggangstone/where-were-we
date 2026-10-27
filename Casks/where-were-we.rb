cask "where-were-we" do
  version "0.7.0"
  sha256 "09a31ce636fec84af11a156c3237c1e11b31dff2a2def386602f94dbbc1d5a07"

  url "https://github.com/ganggangstone/where-were-we/releases/download/v#{version}/where-were-we_#{version}_aarch64-apple-darwin.zip"
  name "where-were-we"
  desc "Local code structure maps for humans and AI agents"
  homepage "https://github.com/ganggangstone/where-were-we"

  depends_on arch: :arm64
  depends_on formula: ["gh", "git"]
  depends_on macos: :big_sur

  app "where-were-we.app"
end
