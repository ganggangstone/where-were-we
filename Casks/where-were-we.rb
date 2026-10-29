cask "where-were-we" do
  version "0.9.0"
  sha256 "9d5ba9f3851bc23a1a5e377cee9d6d8064e89b3323c12d502801f8cb37ce01c0"

  url "https://github.com/ganggangstone/where-were-we/releases/download/v#{version}/where-were-we_#{version}_aarch64-apple-darwin.zip"
  name "where-were-we"
  desc "Local code structure maps for humans and AI agents"
  homepage "https://github.com/ganggangstone/where-were-we"

  depends_on arch: :arm64
  depends_on formula: ["gh", "git"]
  depends_on macos: :big_sur

  app "where-were-we.app"
end
