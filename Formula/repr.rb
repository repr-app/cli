class Repr < Formula
  desc "Privacy-first CLI that analyzes git repositories and generates developer profiles"
  homepage "https://repr.dev"
  version "0.2.19"
  
  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/repr-app/cli/releases/download/v0.2.19/repr-macos.tar.gz"
      sha256 "0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5"
    else
      url "https://github.com/repr-app/cli/releases/download/v0.2.19/repr-macos.tar.gz"
      sha256 "0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5"
    end
  end

  on_linux do
    url "https://github.com/repr-app/cli/releases/download/v0.2.19/repr-linux.tar.gz"
    sha256 "0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5"
  end

  def install
    bin.install "repr"
  end

  test do
    system "#{bin}/repr", "--help"
    system "#{bin}/repr", "config", "--json"
  end
end
