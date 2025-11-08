/*
  ==============================================================================

	BaseComponent.h
	Created: 7 Nov 2025 11:56:15pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "JuceHeader.h"
#include "../layout/WLayout.h"
#include "../../utils/AsyncResizer.h"


class BaseComponent : public Component {
public:

	BaseComponent();
	~BaseComponent();

	void resized() override;

	WLayout& getLayout();
	const WLayout& getLayout() const;
	void setLayout(const WLayout& layout);
	WPreferredSize& getPreferredSize();
	const WPreferredSize& getPreferredSize() const;
	void setPreferredSize(const WPreferredSize& psize);
	WParentLayout* getParentLayout();
	const WParentLayout* getParentLayout() const;
	void setParentLayout(WParentLayout* layout);
	void applyLayout();

	void triggerAsyncResize();
	void setEditor(bool isEditor);

	void addOwnedChildren(Component* c);
	void removeOwnedChildren(Component* c);
	void clearOwnedChildren();
	void ownAndMakeVisible(Component* c);

private:
	WLayout _wlayout;
	WPreferredSize _wPreferredSize;
	std::unique_ptr<WParentLayout> _parentLayout;
	AsyncResizer _asyncResizer;
	WPreferredSize::ListenerLambda _preferredSizeListener;
	std::vector<UPtr<Component>> _ownedChildren;
};

