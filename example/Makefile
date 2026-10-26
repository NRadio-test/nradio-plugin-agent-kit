include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-nradio-demo
PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-nradio-demo
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=NRadio Demo
  DEPENDS:=+libc +luci-base
  PKGARCH:=all
endef

define Package/luci-app-nradio-demo/conffiles
/etc/config/nradio_demo
endef

define Build/Compile
endef

define Package/luci-app-nradio-demo/install
	$(CP) ./root/* $(1)/
	chmod 0755 $(1)/etc/init.d/nradio-demo
	chmod 0755 $(1)/usr/libexec/nradio-demo/worker.sh
endef

define Package/luci-app-nradio-demo/postinst
#!/bin/sh
[ -n "$$IPKG_INSTROOT" ] && exit 0
/etc/init.d/nradio-demo enable
/etc/init.d/nradio-demo restart
rm -f /tmp/luci-indexcache
exit 0
endef

define Package/luci-app-nradio-demo/prerm
#!/bin/sh
[ -n "$$IPKG_INSTROOT" ] && exit 0
/etc/init.d/nradio-demo stop
/etc/init.d/nradio-demo disable
exit 0
endef

define Package/luci-app-nradio-demo/postrm
#!/bin/sh
[ -n "$$IPKG_INSTROOT" ] && exit 0
rm -f /tmp/luci-indexcache
exit 0
endef

$(eval $(call BuildPackage,luci-app-nradio-demo))
