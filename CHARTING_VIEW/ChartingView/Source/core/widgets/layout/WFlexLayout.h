/*
  ==============================================================================

	WFlexLayout.h
	Created: 8 Nov 2025 12:53:22am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "WLayout.h"
#include "../ui/BaseComponent.h"

class WFlexLayout : public WParentLayout {
public:
	enum class Direction { Row, Column };
	enum class JustifyContent { // main axis
		FlexStart,
		FlexEnd,
		Center,
		SpaceBetween,
		SpaceAround,
		SpaceEvenly,
		Stretch
	};
	enum class AlignItems { // cross axis
		Stretch,
		FlexStart,
		FlexEnd,
		Center
	};

	struct Options {
		Direction direction = Direction::Row;
		JustifyContent justify = JustifyContent::FlexStart;
		AlignItems align = AlignItems::Stretch;
		int spacing = 0; // espace entre les enfants

		static Options horizontal_group() {
			Options o;
			o.direction = Direction::Row;
			o.justify = JustifyContent::Stretch;
			o.align = AlignItems::Stretch;
			return o;
		}

		static Options vertical_group() {
			Options o;
			o.direction = Direction::Column;
			o.justify = JustifyContent::Stretch;
			o.align = AlignItems::Stretch;
			return o;
		}

		static Options horizontal_items() {
			Options o;
			o.direction = Direction::Row;
			o.justify = JustifyContent::SpaceAround;
			o.align = AlignItems::FlexStart;
			return o;
		}

		static Options vertical_items() {
			Options o;
			o.direction = Direction::Column;
			o.justify = JustifyContent::SpaceAround;
			o.align = AlignItems::FlexStart;
			return o;
		}
	};

	WFlexLayout(const Options& opts = {});

	void setOptions(const Options& opts);
	const Options& getOptions() const;

	void applyLayout(const Rectangle<int>& bParent, const Array<Component*>& children) override;

private:
	Options options;
};

