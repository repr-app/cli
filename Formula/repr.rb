class Repr < Formula
  desc "Privacy-first CLI that analyzes git repositories and generates developer profiles"
  homepage "https://repr.dev"
  version "0.2.15"
  
  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/repr-app/cli/releases/download/v0.2.15/repr-macos.tar.gz"
      sha256 "f924fd907345af1d3f54f531e3e19258565df09cb42644aaa1848af0e7c1ce57"
    else
      url "https://github.com/repr-app/cli/releases/download/v0.2.15/repr-macos.tar.gz"
      sha256 "f924fd907345af1d3f54f531e3e19258565df09cb42644aaa1848af0e7c1ce57"
    end
  end

  on_linux do
    url "https://github.com/repr-app/cli/releases/download/v0.2.15/repr-linux.tar.gz"
    sha256 "6ea802ec6c03b25fac5cf35fd96f10246b6cb7dca920d0c66a274f7d187a884d"
  end

  def install
    bin.install "repr"
  end

  test do
    system "#{bin}/repr", "--help"
    system "#{bin}/repr", "config", "--json"
  end
end
